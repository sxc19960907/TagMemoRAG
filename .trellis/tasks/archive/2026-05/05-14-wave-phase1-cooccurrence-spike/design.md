# Design — Phase 1：共现矩阵 + V6 spike propagation

## 目的

把 PRD 的 7 个 MVP 块 (M1-M7) 落到模块级契约和数据契约，给 implement.md 一个可执行的步骤蓝图。**研究素材已经在 `research/`**，本设计只重组成实施视角。

## 模块边界

```
┌────────────────────────────────────────────────────────────────────┐
│ Edge: api.py / cli.py — 不动                                       │
└────────────────┬───────────────────────────────────────────────────┘
                 │
┌────────────────▼───────────────────────────────────────────────────┐
│ Search core                                                        │
│   search_runtime.execute_search:                                   │
│     ├─ apply_tag_boost(query_vec, kb_name, settings) ★ NEW HOOK    │
│     │      └─ 仅当 wave_phase1.spike_enabled=true && matrix exists │
│     └─ wave_search(..., disable_legacy_tag_boost=True/False) ★MOD  │
│   wave_searcher.wave_search ★MOD                                   │
│     └─ if disable_legacy_tag_boost: skip chunk-side tag boost      │
└────────────────┬───────────────────────────────────────────────────┘
                 │
┌────────────────▼───────────────────────────────────────────────────┐
│ Phase 1 modules ★ NEW                                              │
│   wave_tag_spike.py:                                               │
│     apply_tag_boost(query_vec, kb_name, settings) → (vec, info)    │
│     propagate(seeds, matrix, residuals, **constants) → energy_map  │
│   tag_cooccurrence.py:                                             │
│     build_cooccurrence_for_kb(kb_name, conn, **knobs) → matrix     │
│     save_cooccurrence(path, matrix) / load_cooccurrence(path)      │
└────────────────┬───────────────────────────────────────────────────┘
                 │
┌────────────────▼───────────────────────────────────────────────────┐
│ Rebuild lifecycle                                                  │
│   tag_rebuild.sync_rebuild_tags ★MOD                               │
│     └─ 末尾追加 build_cooccurrence_for_kb + save                   │
│   state.RebuildTask ★MOD: + tag_cooccurrence_edges/error           │
└────────────────┬───────────────────────────────────────────────────┘
                 │
┌────────────────▼───────────────────────────────────────────────────┐
│ Storage                                                            │
│   data/_global/tag_cooccurrence/{kb_name}.npz ★ NEW                │
│   SQLite: 复用 Phase 0 schema (manual_tags / tags / residuals)     │
└────────────────────────────────────────────────────────────────────┘
```

## 数据契约

### CooccurrenceMatrix (内存)

```python
@dataclass(frozen=True)
class CooccurrenceMatrix:
    kb_name: str
    edges: dict[int, dict[int, float]]   # source_tag_id → {target_tag_id: weight}
    built_at: str                         # ISO timestamp
    edge_count: int                       # len(flatten edges)

    def neighbors(self, tag_id: int) -> dict[int, float]:
        return self.edges.get(tag_id, {})
```

`dict[int, dict[int, float]]` 选型理由见 `research/python-port-mapping.md`。`weight` 是 float（accumulated phi-pair across files），可能 ≥1.0（触发 wormhole）。

### NPZ 持久化格式

```
data/_global/tag_cooccurrence/{kb_name}.npz
  schema_version: int32                 # 当前 1
  meta_kb_name:   str (object array)
  meta_built_at:  str (object array)
  source_ids:     int64[E]              # E = edge_count
  target_ids:     int64[E]
  weights:        float32[E]
```

写入用 atomic write（tmp → fsync → replace → fsync(dir)），与 `epa_basis.save_epa_basis` 模式一致。
load 失败（文件损坏 / schema_version 不匹配）⇒ 返回 None，**不抛异常**，让 search 自然短路。

### Spike propagation IO

```python
@dataclass(frozen=True)
class SpikeResult:
    accumulated_energy: dict[int, float]    # tag_id → total accumulated energy
    seed_count: int
    emergent_count: int
    hops_executed: int
    truncated_by_cap: bool                  # 任何 cap (hops/emergent/neighbors) 触发

def propagate(
    seed_weights: dict[int, float],
    matrix: CooccurrenceMatrix,
    residuals: dict[int, float],            # tag_id → residual_energy, 缺值默认 1.0
    *,
    max_hops: int = 4,
    base_momentum: float = 2.0,
    firing_threshold: float = 0.10,
    base_decay: float = 0.25,
    wormhole_decay: float = 0.70,
    tension_threshold: float = 1.0,
    max_neighbors: int = 20,
    max_emergent: int = 50,
) -> SpikeResult: ...
```

参数默认值与源 `srConfig` 一致（`research/source-tag-boost-and-spike.md` § [4.5]）。

### apply_tag_boost IO

```python
@dataclass(frozen=True)
class TagBoostInfo:
    seed_tag_ids: list[int]
    seed_count: int
    emergent_count: int
    matched_tag_names: list[str]            # for debug payload
    boost_factor_applied: float             # alpha actually used
    matrix_loaded: bool
    skipped_reason: str = ""                # "matrix_missing" / "no_seeds" / "spike_disabled"

def apply_tag_boost(
    query_vec: np.ndarray,
    *,
    kb_name: str,
    settings: Settings,
    base_tag_boost: float,
    embedder=None,                          # 仅做 type forwarding，向量已在 query_vec 里
) -> tuple[np.ndarray, TagBoostInfo]: ...
```

返回 `(boosted_vec, info)`。当跳过时返回 `(query_vec, info_with_skipped_reason)`，调用方判断 `skipped_reason` 决定是否记日志。

## 关键算法步骤

### Builder（M1 / `tag_cooccurrence.build_cooccurrence_for_kb`）

```python
def build_cooccurrence_for_kb(kb_name, conn, *, phi_max=0.9, phi_min=0.5,
                              legacy_phi=0.7, max_tags_per_manual=100):
    # Step 1: 每 manual 的 tag 数（用于性能 guard）
    rows = conn.execute(
        "SELECT manual_id, tag_id, position FROM manual_tags "
        "WHERE kb_name=? AND position > 0 ORDER BY manual_id, position ASC",
        (kb_name,),
    )
    edges: dict[int, dict[int, float]] = {}
    current_manual: str | None = None
    pending: list[tuple[int, int]] = []  # (tag_id, position)

    def flush(tags):
        n = len(tags)
        if n < 2 or n > max_tags_per_manual:
            return
        for i in range(n):
            for j in range(i + 1, n):
                t1, p1 = tags[i]
                t2, p2 = tags[j]
                phi1 = phi_max - (phi_max - phi_min) * (p1 - 1) / (n - 1)
                phi2 = phi_max - (phi_max - phi_min) * (p2 - 1) / (n - 1)
                w = phi1 * phi2
                edges.setdefault(t1, {})[t2] = edges.get(t1, {}).get(t2, 0.0) + w

    for row in rows:
        if row["manual_id"] != current_manual:
            if pending:
                flush(pending)
            current_manual = row["manual_id"]
            pending = []
        pending.append((row["tag_id"], row["position"]))
    if pending:
        flush(pending)

    # Step 3: legacy fallback (position=0)
    legacy_rows = conn.execute(
        "SELECT ft1.tag_id AS t1, ft2.tag_id AS t2, COUNT(ft1.manual_id) AS cnt "
        "FROM manual_tags ft1 JOIN manual_tags ft2 "
        "ON ft1.kb_name=ft2.kb_name AND ft1.manual_id=ft2.manual_id "
        "AND ft1.tag_id < ft2.tag_id "
        "WHERE ft1.kb_name=? AND (ft1.position=0 OR ft2.position=0) "
        "GROUP BY ft1.tag_id, ft2.tag_id",
        (kb_name,),
    )
    for row in legacy_rows:
        w = row["cnt"] * legacy_phi * legacy_phi
        edges.setdefault(row["t1"], {})[row["t2"]] = edges.get(row["t1"], {}).get(row["t2"], 0.0) + w
        edges.setdefault(row["t2"], {})[row["t1"]] = edges.get(row["t2"], {}).get(row["t1"], 0.0) + w

    return CooccurrenceMatrix(
        kb_name=kb_name,
        edges=edges,
        built_at=_now(),
        edge_count=sum(len(v) for v in edges.values()),
    )
```

### Spike propagation（M2 / `wave_tag_spike.propagate`）

直接照搬源 [4.5] 段，结构对应：
- `activeSpikes: Map<id, {energy, momentum}>` → `dict[int, tuple[float, float]]`
- `accumulatedEnergy: Map<id, float>` → `dict[int, float]`
- 每 hop 内层循环按 weight 降序取前 `max_neighbors` 个邻居
- wormhole 判定：`tension = coocWeight * residual >= tension_threshold`
- 末尾 `truncated_by_cap` 在 hops 用满 / emergent_count > max_emergent / 任何节点 neighbors > max_neighbors 时设 True（用于 metric & debug）

### apply_tag_boost（M3 / `wave_tag_spike.apply_tag_boost`）

```python
def apply_tag_boost(query_vec, *, kb_name, settings, base_tag_boost, embedder=None):
    if not settings.wave_phase1.spike_enabled:
        return query_vec, TagBoostInfo(skipped_reason="spike_disabled", ...)

    matrix = _load_matrix_cached(kb_name, _matrix_path(settings, kb_name))
    if matrix is None or matrix.edge_count == 0:
        return query_vec, TagBoostInfo(skipped_reason="matrix_missing", ...)

    # Step 1 — Seed selection (top-K cosine)
    seeds = _select_seeds(query_vec, kb_name, settings,
                          top_k=settings.wave_phase1.seed_top_k,
                          min_similarity=settings.wave_phase1.seed_min_similarity)
    if not seeds:
        return query_vec, TagBoostInfo(skipped_reason="no_seeds", ...)

    # Step 2 — Spike propagation
    residuals = _load_residuals(kb_name, settings)   # default 1.0
    spike = propagate(
        seed_weights={tid: sim for tid, _name, sim in seeds},
        matrix=matrix,
        residuals=residuals,
        max_hops=settings.wave_phase1.spike_max_hops,
        ... (其他常数)
    )

    # Step 3 — Merge seeds + emergent, semantic dedup
    candidate_tags = _merge_and_dedup(seeds, spike,
                                      settings.wave_phase1.dedup_threshold,
                                      settings.wave_phase1.dedup_weight_transfer,
                                      kb_name, settings)

    # Step 4 — Weighted-mean context vector + L2 normalize
    context = _weighted_context(candidate_tags, dim=query_vec.shape[0])
    if np.linalg.norm(context) < 1e-9:
        return query_vec, TagBoostInfo(skipped_reason="degenerate_context", ...)

    # Step 5 — Fuse with alpha
    if settings.wave_phase1.dynamic_boost_factor_strategy == "epa":
        dynamic = _epa_dynamic_boost(query_vec, settings)  # uses epa_projector.project()
    else:
        dynamic = 1.0
    effective_boost = base_tag_boost * np.clip(
        dynamic,
        settings.wave_phase1.dynamic_boost_min,
        settings.wave_phase1.dynamic_boost_max,
    )
    alpha = float(min(1.0, effective_boost))
    fused = (1 - alpha) * query_vec + alpha * context
    fused /= np.linalg.norm(fused) + 1e-9
    return fused, TagBoostInfo(boost_factor_applied=alpha, ...)
```

### Loader 缓存

```python
@dataclasses.dataclass(frozen=True)
class _MatrixCacheKey:
    kb_name: str
    mtime_ns: int

_MATRIX_CACHE: dict[_MatrixCacheKey, CooccurrenceMatrix | None] = {}

def _load_matrix_cached(kb_name, path):
    if not path.exists():
        return None
    key = _MatrixCacheKey(kb_name, path.stat().st_mtime_ns)
    if key not in _MATRIX_CACHE:
        # 限制缓存大小：>16 项时清最早
        if len(_MATRIX_CACHE) >= 16:
            _MATRIX_CACHE.pop(next(iter(_MATRIX_CACHE)))
        _MATRIX_CACHE[key] = load_cooccurrence(path)
    return _MATRIX_CACHE[key]
```

mtime_ns 作为 cache key 一部分，rebuild 写新文件后下次 search 自动失效旧缓存。

## 集成点的细节

### search_runtime.execute_search 修改

```python
def execute_search(*, state, query_vec, settings, top_k, ..., query_text=""):
    filter_dict = dict(filters or {})
    filtered_node_ids = filter_node_ids(state.graph, filter_dict)

    # ... 现有 lexical + ANN 段 ...

    # ★ NEW: tag boost 在 ANN/lexical 之后，wave_search 之前
    boost_info: TagBoostInfo | None = None
    legacy_tag_boost_disabled = False
    if settings.wave_phase1.spike_enabled and settings.wave_phase1.cooccurrence_enabled:
        from .wave_tag_spike import apply_tag_boost
        boosted_vec, boost_info = apply_tag_boost(
            query_vec=query_vec,
            kb_name=state.kb_name,
            settings=settings,
            base_tag_boost=settings.search.tag_boost,
        )
        if boost_info.boost_factor_applied > 0:
            query_vec = boosted_vec
            legacy_tag_boost_disabled = not settings.wave_phase1.legacy_chunk_tag_boost

    results = wave_search(
        query_vec, state.graph, state.vectors, state.anchors,
        ...,
        disable_legacy_tag_boost=legacy_tag_boost_disabled,
    )

    return SearchExecution(
        ...,
        tag_boost_info=boost_info,    # ★ NEW field
    )
```

### wave_searcher.wave_search 修改

参数 `disable_legacy_tag_boost: bool = False`。在现有 metadata field boost 段中，遇到 `field == "tags"` 时跳过加分。其他 metadata field（brand/category/model/language）不受影响 — D3 锁的是 tags 维度避免与 query-vector boost 双算。

### tag_rebuild.sync_rebuild_tags 修改

```python
def sync_rebuild_tags(kb_name, cfg, *, manual_tags_by_id, embedder, ...):
    ... 现有 manual_tags upsert + 孤儿清理 + tag embedding ...

    # Phase 0: EPA 重训
    epa_report = retrain_report(cfg)

    # ★ Phase 1: 共现矩阵重建
    cooc_report = build_and_save_cooccurrence(kb_name, cfg)

    return TagRebuildReport(
        ...,
        tag_cooccurrence_edges=cooc_report.edge_count,
        tag_cooccurrence_error=cooc_report.error_type,
    )
```

`build_and_save_cooccurrence` 是个 thin wrapper：
- 包 try/except，失败返回 `error_type=type(exc).__name__`
- empty matrix（edge_count=0）⇒ 不写文件，返回 `edge_count=0, error_type=""`
- 成功 ⇒ atomic write 到 `data/_global/tag_cooccurrence/{kb_name}.npz`

### state.RebuildTask 修改

```python
@dataclass
class RebuildTask:
    ...
    tag_cooccurrence_edges: int = 0
    tag_cooccurrence_error: str = ""
```

`to_dict` 跟着加这两字段。`incremental_rebuild` / `state.build_kb` 的 detail propagation 跟着加（与 Phase 0 9 个 epa/tag 字段同模式，已经有现成参考）。

### config.py 新增

```python
class WavePhase1Config(BaseSettings):
    enabled: bool = True
    spike_enabled: bool = False
    cooccurrence_enabled: bool = True

    # cooccurrence builder
    phi_max: float = 0.9
    phi_min: float = 0.5
    legacy_phi: float = 0.7
    max_tags_per_manual: int = 100

    # spike algorithm
    spike_max_hops: int = 4
    spike_base_momentum: float = 2.0
    spike_firing_threshold: float = 0.10
    spike_base_decay: float = 0.25
    spike_wormhole_decay: float = 0.70
    spike_tension_threshold: float = 1.0
    spike_max_emergent_nodes: int = 50
    spike_max_neighbors_per_node: int = 20

    # seed selection
    seed_top_k: int = 8
    seed_min_similarity: float = 0.3

    # boost factor strategy
    dynamic_boost_factor_strategy: Literal["constant", "epa"] = "constant"
    dynamic_boost_min: float = 0.3
    dynamic_boost_max: float = 2.0

    # semantic dedup
    dedup_threshold: float = 0.88
    dedup_weight_transfer: float = 0.2

    # compatibility
    legacy_chunk_tag_boost: bool = False
```

### config.yaml 加段（spike_enabled: false 默认）

```yaml
wave_phase1:
  enabled: true
  spike_enabled: false           # ★ 默认关闭，需运维显式打开
  cooccurrence_enabled: true
  # builder constants
  phi_max: 0.9
  phi_min: 0.5
  legacy_phi: 0.7
  max_tags_per_manual: 100
  # spike constants
  spike_max_hops: 4
  spike_base_momentum: 2.0
  spike_firing_threshold: 0.10
  spike_base_decay: 0.25
  spike_wormhole_decay: 0.70
  spike_tension_threshold: 1.0
  spike_max_emergent_nodes: 50
  spike_max_neighbors_per_node: 20
  # seed
  seed_top_k: 8
  seed_min_similarity: 0.3
  # boost
  dynamic_boost_factor_strategy: constant
  dynamic_boost_min: 0.3
  dynamic_boost_max: 2.0
  # dedup
  dedup_threshold: 0.88
  dedup_weight_transfer: 0.2
  # compat
  legacy_chunk_tag_boost: false
```

## 失败 / 降级语义

| 场景 | 行为 |
|---|---|
| `spike_enabled=false` | search_runtime 完全跳过 apply_tag_boost；输出与 master 一致 |
| `cooccurrence_enabled=false` | rebuild 不构建矩阵；search 加载时见缺文件 ⇒ 短路 |
| matrix 文件损坏 / schema 不匹配 | `load_cooccurrence` 返回 None；search 短路 |
| 矩阵存在但 `edge_count=0` | search 短路（不写空文件，所以正常情况见不到这个） |
| seeds 为空（top-K 后 cosine 都低于阈值） | `apply_tag_boost` 返回原 query；BoostInfo.skipped_reason="no_seeds" |
| spike 后 contextVec 退化（all-zero / norm < 1e-9） | 返回原 query；BoostInfo.skipped_reason="degenerate_context" |
| rebuild 时 builder 抛异常 | rebuild status 仍 "done"；`tag_cooccurrence_error` 字段记 type；下次 rebuild 重建 |
| 矩阵写盘失败（IO 错误） | 同上，error_type 记 IOError，旧文件保留 |

## 可观测

3 个 Prometheus 指标新增（label 全部低基数，遵循 Phase 0 标准）：

```python
self.tag_cooccurrence_edges = Gauge(
    "tagmemorag_tag_cooccurrence_edges",
    "Directed cooccurrence edge count by KB.",
    ["kb_name"], registry=registry)

self.tag_cooccurrence_rebuild_duration = Histogram(
    "tagmemorag_tag_cooccurrence_rebuild_duration_seconds",
    "Cooccurrence matrix rebuild duration.",
    ["kb_name", "outcome"], registry=registry,
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0))

self.tag_spike_propagations = Counter(
    "tagmemorag_tag_spike_propagations_total",
    "Spike propagation invocations by outcome.",
    ["kb_name", "outcome"], registry=registry)
# outcome: "applied" / "skipped" / "error"
```

`record_*` helpers 加在 `Metrics` 类，与 Phase 0 模式对齐。`outcome` 限定为低基数集合（不带 reason 后缀避免 cardinality 漂移），具体 skipped reason 走 BoostInfo + structured log。

## 兼容性

| 维度 | 行为 |
|---|---|
| 旧 `search.tag_boost` knob | 数值不动；spike on + legacy off 时 chunk-side 不消费 |
| Phase 0 e2e baseline 不变性 (`test_search_baseline_invariance`) | spike off 默认下保持过 |
| 现有 SiliconFlow 部署 | 不动 baseline；运维启用 spike 时本地跑 sanity 后再上线 |
| 老 config.yaml 没 wave_phase1 段 | pydantic 默认值兜住，行为等同 spike off |
| 旧 manual_registry.sqlite3 | 不动；仅读 manual_tags 表 |

## 回滚

```yaml
# 软回滚（不删数据）
wave_phase1:
  spike_enabled: false
```

```bash
# 硬回滚（删数据 + revert）
rm -rf data/_global/tag_cooccurrence/
git revert <phase1-commit-range>
```

## Open implementation questions（实施时回答）

1. `_select_seeds` 用 SQL JOIN 还是先取所有 vectors 再 numpy？fixture 规模下都行；建议"先 SQL 拿 id+vec 后 numpy 算余弦"，复用 `iter_canonical_tags_with_vectors`
2. `_load_residuals` 读 `tag_intrinsic_residuals` 表还是直接默认 1.0？默认 1.0，不读表（Phase 1 residual 都是 1.0），等 Phase 3 接 ResidualPyramid 时再扩展
3. `wave_search` 的 `disable_legacy_tag_boost` 参数风格？建议 keyword-only，不破坏现有调用方

