# Technical Design — Phase 4 V8 geodesicRerank

> 父文档：[prd.md](./prd.md)
> 上游 Phase：3（detectCrossDomainResonance）+ 3.5（intrinsic_residuals）
> 下游 Phase：无（V8 是 wave 主线最后一块）

## 1. 模块边界

```
search_runtime.execute_search
  ├─ apply_tag_boost (existing)
  │   └─ propagate → SpikeResult.accumulated_energy
  │       ↓ NEW: 透传到 TagBoostInfo.accumulated_energy
  ├─ wave_search(rerank_pool_size=pool)            ← NEW 参数
  │   └─ 返回 list[Result]（长度 = pool 或更少）
  ├─ geodesic_rerank(...)                          ← NEW 模块
  │   └─ 返回 list[Result]（长度同输入，已重排）
  └─ 截 top_k
```

依赖方向严格自上而下，`geodesic_rerank` 不知道 `execute_search` 存在，便于纯函数单测。

## 2. 数据契约

### 2.1 `TagBoostInfo` 扩展

```python
@dataclass
class TagBoostInfo:
    # ... 现有字段保持不变 ...
    accumulated_energy: Mapping[int, float] | None = None
```

- spike 成功路径：`accumulated_energy = MappingProxyType(spike_result.accumulated_energy)` 或直接 dict 浅拷贝（避免外部误改）。
- 任何 skipped_reason 早返回路径：`accumulated_energy = None`。
- `to_dict`/debug payload：默认排除 raw dict，仅输出 `geodesic_energy_field_size: int = len(accumulated_energy or {})`。

### 2.2 V8 入参 / 出参

```python
@dataclass(frozen=True)
class GeodesicRerankResult:
    candidates: list[Result]                # 重排后顺序
    swap_kinds: dict[str, int]              # {"rank_changed": int, "new_entry": int, "lost_entry": int}
    skipped_reason: str | None              # None ⇒ 实际跑了；非 None ⇒ 退化（reason 入 metric label）
    hit_count_observed: tuple[int, ...]     # 每候选的 hitCount，按入参顺序排列
    max_geo: float                          # 归一化前的最大 geoScore
    applied: bool                           # True 当且仅当 skipped_reason is None and max_geo > 0


def geodesic_rerank(
    candidates: Sequence[Result],
    *,
    energy_field: Mapping[int, float] | None,
    graph: nx.Graph,
    kb_name: str,
    settings: Settings,
    top_k: int,
    alpha: float | None = None,             # None ⇒ 用 settings 默认
    min_geo_samples: int | None = None,     # None ⇒ 用 settings 默认
) -> GeodesicRerankResult: ...
```

- **不修改输入** `candidates` — 返回新 list；元素可加诊断字段（`geo_score / normalized_geo / geo_hit_count / original_knn_score`），通过 `Result.with_extras(...)` 或 dataclass `replace`。
- **swap_kinds 计算**：以「重排前 top_k 集合 vs 重排后 top_k 集合」为基准：
  - `rank_changed`：重排前后都在 top_k 但位置变了。
  - `new_entry`：重排后进入 top_k 的（原本在 K..K' 区间）。
  - `lost_entry`：重排前在 top_k 但被挤出去的。
  注意：算 swap 必须基于 input candidates 的顺序，而 input 是 `wave_search(rerank_pool_size=pool)` 已按分降序的列表，所以 input[:top_k] 即重排前 top_k。

### 2.3 chunk → tag_id 解析

```python
def _resolve_chunk_tag_ids(graph, node_id, *, kb_name, settings) -> list[int]:
    metadata = metadata_from_node(graph.nodes[node_id])
    raw_tags = metadata.get("tags") or []
    if not isinstance(raw_tags, list):
        return []
    norm_names = [normalize_tag(str(t)) for t in raw_tags]
    return [tid for tid in (lookup_tag_id(kb_name, name, settings=settings) for name in norm_names) if tid is not None]
```

- `tag_store.lookup_tag_id` 已在仓内被 `_resolve_core_tag_set` 等多处复用，是稳定接口。
- 缺失/解析失败的 tag 直接跳过，不影响其他 tag 累加；hitCount 只算成功解析到 tag_id 的部分。

## 3. 核心算法（伪代码）

```python
def geodesic_rerank(candidates, *, energy_field, graph, kb_name, settings, top_k,
                    alpha=None, min_geo_samples=None):
    cfg = settings.wave_phase1
    alpha = alpha if alpha is not None else cfg.geodesic_alpha
    alpha = max(0.0, min(1.0, alpha))   # clamp 防御
    min_samples = min_geo_samples if min_geo_samples is not None else cfg.geodesic_min_geo_samples

    # L0
    if not energy_field:
        return GeodesicRerankResult(list(candidates), _zero_swaps(), "energy_field_empty", (), 0.0, False)
    if not candidates:
        return GeodesicRerankResult([], _zero_swaps(), "no_candidates", (), 0.0, False)

    # Step 1+2 合并：每候选直接从 metadata 拿 tag_ids
    geo_data = []
    hit_counts = []
    max_geo = 0.0
    for c in candidates:
        tag_ids = _resolve_chunk_tag_ids(graph, c.node_id, kb_name=kb_name, settings=settings)
        total = 0.0
        hits = 0
        for tid in tag_ids:
            energy = energy_field.get(int(tid))
            if energy is not None:
                total += float(energy)
                hits += 1
        # L1
        geo_score = (total / hits) if hits >= min_samples else 0.0  # Phase 4.1: replace _score_aggregator
        if geo_score > max_geo:
            max_geo = geo_score
        geo_data.append((c, geo_score, hits, total))
        hit_counts.append(hits)

    # L2
    if max_geo == 0.0:
        return GeodesicRerankResult(list(candidates), _zero_swaps(), "max_geo_zero", tuple(hit_counts), 0.0, False)

    # Step 4: blend + Step 5: sort
    reranked = []
    for c, geo, hits, total in geo_data:
        norm_geo = geo / max_geo
        knn = float(c.score)
        final = (1.0 - alpha) * knn + alpha * norm_geo
        reranked.append(c.with_extras(
            score=final,
            original_knn_score=knn,
            geo_score=geo,
            normalized_geo=norm_geo,
            geo_hit_count=hits,
        ))
    reranked.sort(key=lambda r: (-r.score, r.node_id))   # tie-break by node_id 稳定

    # 计算 swap_kinds
    before_top = {c.node_id for c in candidates[:top_k]}
    after_top = {c.node_id for c in reranked[:top_k]}
    new_entry = len(after_top - before_top)
    lost_entry = len(before_top - after_top)
    rank_changed = sum(
        1 for i, r in enumerate(reranked[:top_k])
        if r.node_id in before_top and candidates.index(_find_by_id(candidates, r.node_id)) != i
    )

    return GeodesicRerankResult(
        candidates=reranked,
        swap_kinds={"rank_changed": rank_changed, "new_entry": new_entry, "lost_entry": lost_entry},
        skipped_reason=None,
        hit_count_observed=tuple(hit_counts),
        max_geo=max_geo,
        applied=True,
    )
```

**复杂度**：N = 候选数（top_k × oversample，通常 ≤ 40）。每候选 O(T) tag 解析 + O(T) energy 累加（T = 平均 tag 数 ≈ 3）。总 O(N·T) ≈ 120 次 dict lookup，<1ms。

## 4. `wave_search` 的 `rerank_pool_size` 参数

```python
def wave_search(..., rerank_pool_size: int | None = None, ...) -> list[Result]:
    # ... 现有逻辑保持不变 ...
    ranked = sorted(boosted.items(), key=lambda item: (-item[1], item[0]))
    if rerank_pool_size is not None:
        ranked = ranked[: max(int(rerank_pool_size), 0)]
    else:
        ranked = ranked[:top_k]
    return [_make_result(graph, node_id, score) for node_id, score in ranked]
```

- `rerank_pool_size=None` 路径与现状字节相等（baseline invariance 锁底）。
- `rerank_pool_size >= top_k` 是调用方约定，传入小于 top_k 由调用方负责（V8 不会越界，但语义就是 oversample）。

## 5. `execute_search` 接入

```python
# 现有 wave_search 调用之前：
phase1 = settings.wave_phase1
v8_should_run = (
    phase1.enabled
    and phase1.spike_enabled
    and phase1.geodesic_rerank_enabled
    and boost_info is not None
    and boost_info.skipped_reason is None
    and boost_info.accumulated_energy
)

if v8_should_run:
    pool = max(top_k, math.ceil(top_k * phase1.geodesic_oversample_factor))
    candidates = wave_search(..., rerank_pool_size=pool)
    rerank_result = geodesic_rerank(
        candidates,
        energy_field=boost_info.accumulated_energy,
        graph=state.graph,
        kb_name=state.kb_name,
        settings=settings,
        top_k=top_k,
    )
    _record_geodesic_metrics(kb_name=state.kb_name, rerank_result=rerank_result)
    results = rerank_result.candidates[:top_k]
else:
    results = wave_search(..., rerank_pool_size=None)
    if phase1.geodesic_rerank_enabled:
        # 翻开 flag 但实际没跑 ⇒ 记 skipped reason
        reason = _classify_skipped_reason(boost_info, ann_strategy=strategy)
        get_metrics().record_geodesic_rerank_skipped(kb_name=state.kb_name, reason=reason)
```

`_classify_skipped_reason`：
```python
def _classify_skipped_reason(boost_info, ann_strategy):
    if boost_info is None:
        return "lexical_only_path"
    if boost_info.skipped_reason == "spike_disabled":
        return "spike_disabled"
    if boost_info.skipped_reason in {
        "matrix_missing", "no_tag_vectors", "no_seeds", "no_candidates",
        "degenerate_context", "zero_alpha", "degenerate_fused",
    }:
        return boost_info.skipped_reason
    if not boost_info.accumulated_energy:
        return "energy_field_empty"
    return "unknown"
```

## 6. Observability

| Metric | Type | Labels | When Recorded |
|--------|------|--------|---------------|
| `tagmemorag_geodesic_rerank_applied_total` | Counter | `kb_name` | V8 实跑成功 (`applied=True`) |
| `tagmemorag_geodesic_rerank_skipped_total` | Counter | `kb_name`, `reason` | V8 想跑但退化（含 enabled=true 但前置不满足） |
| `tagmemorag_geodesic_rerank_swap_total` | Counter | `kb_name`, `kind` | applied=True 时按 swap_kinds 累加 |
| `tagmemorag_geodesic_rerank_hit_count_observed` | Histogram | `kb_name` | applied=True 时每候选 hitCount 入桶（buckets: 0,1,2,3,4,6,10) |

`reason` 白名单（写入 allowed labels）：`spike_disabled / matrix_missing / no_tag_vectors / no_seeds / no_candidates / degenerate_context / zero_alpha / degenerate_fused / energy_field_empty / max_geo_zero / lexical_only_path / unknown`。

## 7. Configuration

```python
class WavePhase1Settings(BaseModel):
    # ... 现有字段保持不变 ...
    geodesic_rerank_enabled: bool = False
    geodesic_alpha: float = 0.3
    geodesic_oversample_factor: float = 2.0
    geodesic_min_geo_samples: int = 2

    @field_validator("geodesic_alpha")
    @classmethod
    def _clamp_alpha(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    @field_validator("geodesic_oversample_factor")
    @classmethod
    def _validate_oversample(cls, v: float) -> float:
        if float(v) < 1.0:
            raise ValueError("geodesic_oversample_factor must be >= 1.0")
        return float(v)

    @field_validator("geodesic_min_geo_samples")
    @classmethod
    def _validate_min_samples(cls, v: int) -> int:
        if int(v) < 1:
            raise ValueError("geodesic_min_geo_samples must be >= 1")
        return int(v)
```

## 8. 兼容性保证（baseline invariance）

| 场景 | flag-off 路径 | 期望行为 |
|------|--------------|----------|
| `geodesic_rerank_enabled=False` | `wave_search(rerank_pool_size=None)` 直接截 top_k | 与现状字节相等（hashing eval 8 套 + e2e baseline） |
| `geodesic_rerank_enabled=True` 但 `spike_enabled=False` | V8 silent noop，记 `skipped_reason=spike_disabled` | top_k 与现状字节相等 |
| `geodesic_rerank_enabled=True` + lexical-only fallback | V8 silent noop，记 `skipped_reason=lexical_only_path` | top_k 与现状字节相等 |
| `geodesic_rerank_enabled=True` + spike 跑通 + max_geo=0 | V8 跑了 L1，归一化前 maxGeo=0，返回原顺序，记 `skipped_reason=max_geo_zero` | top_k 与现状字节相等 |

## 9. Rollout / Rollback

- Rollout：默认 false，逐 KB 翻开（`POST /admin/config` 或 reload）。先跑 diag 脚本看 `max_geo_zero` 占比和 hit_count 直方图，确认 `min_samples` 设置合理后再翻 flag。
- Rollback：把 `geodesic_rerank_enabled` 设回 false，下一次请求即回到 baseline 路径。所有缓存、表、写入磁盘的状态都不依赖此 flag。

## 10. 扩展点（Phase 4.1+）

- 评分函数：`_score_aggregator(total, hits)` 当前硬编码 `total/hits`，未来可参数化为 `mean / sum / log_norm / max_pool` strategy lookup。
- α 请求级覆盖：`POST /search` 增加 `geodesic_alpha: float | None`，None ⇒ 用 settings；向后兼容地新增。
- 跨 query 能量场缓存：在 `apply_tag_boost` 入口加 cache key（query_hash + kb_name + matrix_built_at），命中即跳过 spike，直接走 V8。

## 附：字段可追溯性

| PRD 决策 | design.md 对应段 |
|---------|------------------|
| D1 硬依赖 + silent noop | §5 `v8_should_run` 表达式 + `_classify_skipped_reason` |
| D2 oversample factor | §4 `rerank_pool_size` + §5 `pool` 计算 |
| D3 min_geo_samples=2 | §3 L1 防御 + §7 settings |
| D4 α config-only | §7 settings + §3 alpha clamp |
| D5 TagBoostInfo.accumulated_energy | §2.1 |
| D6 MVP scope | §6 metric 集合 + §3 swap_kinds + §4 baseline invariance |
| D7 reason 细分 | §6 reason 白名单 + §5 `_classify_skipped_reason` |
