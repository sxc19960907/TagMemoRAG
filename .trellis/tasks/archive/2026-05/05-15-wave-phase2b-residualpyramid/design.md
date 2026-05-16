# Design — Phase 2b-1: ResidualPyramid + 完整 dynamicBoostFactor 公式 + 观测补齐

## 目的

把 PRD 的 D2-D7 决策落到模块级契约 + 数据契约 + 关键算法步骤 + 失败语义。Phase 2b-1 是 **Complex 任务**（新增模块 + 修改核心搜索路径 + 观测扩展），本设计覆盖：模块边界、数据契约、关键算法步骤、失败/降级语义、兼容性、回滚。

## 模块边界

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Edge: api.py / cli.py — 不动                                             │
└──────────────────┬───────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────────────────────────┐
│ Search core                                                              │
│   wave_tag_spike._resolve_dynamic_boost ★MOD                             │
│     └─ strategy="pyramid" 路径：完整公式 + ResidualPyramid 调用          │
│   wave_tag_spike.apply_tag_boost ★MOD                                    │
│     └─ strategy="pyramid" 时换 seed selector：levels[*].tags + decay     │
│   search_runtime.execute_search — 不动                                   │
└──────────────────┬───────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────────────────────────┐
│ ResidualPyramid (NEW)                                                    │
│   src/tagmemorag/residual_pyramid.py ★ NEW                               │
│     ResidualPyramid(tag_rows, config) — 实例化时拿全量 tag 行           │
│     analyze(query_vec) -> PyramidResult                                  │
│       └─ 多级 Modified Gram-Schmidt + level-0 handshake + features       │
└──────────────────┬───────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────────────────────────┐
│ EPA (existing)                                                           │
│   epa_projector.EPAProjector.project — 已返 logicDepth / entropy         │
│     ★ Phase 2b-1 复用 entropy（之前只用 logicDepth）                      │
└──────────────────┬───────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────────────────────────┐
│ Config                                                                   │
│   config.WavePhase1Config ★MOD                                           │
│     + dynamic_boost_factor_strategy: Literal[constant, epa, pyramid]     │
│     + pyramid_max_levels: int = 3                                        │
│     + pyramid_top_k: int = 10                                            │
│     + pyramid_min_energy_ratio: float = 0.1                              │
│     + pyramid_layer_decay_base: float = 0.7                              │
│     + activation_multiplier_min: float = 0.5                             │
│     + activation_multiplier_max: float = 1.5                             │
│     + pyramid_use_handshake_features: bool = True (D2 fallback knob)     │
│   config.yaml ★MOD: 同步                                                 │
└──────────────────┬───────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────────────────────────┐
│ Observability ★MOD                                                       │
│   observability/metrics.py                                               │
│     + tag_dynamic_factor: Histogram(kb_name, strategy)                   │
│     + tag_pyramid_levels: Histogram(kb_name)                             │
│     + tag_pyramid_explained_energy: Histogram(kb_name)                   │
│     + tag_pyramid_features: Gauge(kb_name, feature)                      │
│     + record_tag_dynamic_factor / record_tag_pyramid_*                   │
└──────────────────┬───────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────────────────────────┐
│ Diagnostics & Tests                                                      │
│   scripts/diag_pyramid_dynamic_boost.py ★ NEW                            │
│   tests/unit/test_residual_pyramid.py ★ NEW (≥6 段)                      │
│   tests/unit/test_apply_tag_boost.py ★MOD (+3 段 strategy=pyramid)       │
│   tests/unit/test_observability_metrics.py ★MOD (+用例)                  │
└──────────────────────────────────────────────────────────────────────────┘
```

## 数据契约

### `residual_pyramid.py` 新数据类

```python
@dataclass(frozen=True)
class PyramidLevel:
    level: int                         # 0-indexed
    tags: tuple[PyramidTag, ...]       # 该级 top-K candidates
    projection_magnitude: float
    residual_magnitude: float
    residual_energy_ratio: float       # ||residual||² / originalEnergy
    energy_explained: float            # 本级解释的能量比例
    handshake_features: HandshakeFeatures | None  # 仅 level-0 计算

@dataclass(frozen=True)
class PyramidTag:
    tag_id: int
    name: str
    similarity: float                  # tagIndex.search 返的 score
    contribution: float                # basis_coefficients[i] 的绝对值
    handshake_magnitude: float         # 仅 level-0 有意义，其他级填 0

@dataclass(frozen=True)
class HandshakeFeatures:
    direction_coherence: float         # ||mean(direction_i)||
    pattern_strength: float            # 前 5 个方向两两点积绝对值均值
    novelty_signal: float              # = direction_coherence
    noise_signal: float                # (1 - dc) * (1 - pps)

@dataclass(frozen=True)
class PyramidFeatures:
    depth: int                         # = len(levels)
    coverage: float                    # min(1.0, totalExplainedEnergy)
    novelty: float                     # residual_ratio*0.7 + dir_novelty*0.3
    coherence: float                   # = handshake.pattern_strength (level-0)
    tag_memo_activation: float         # = coverage * coherence * (1 - noise)
    expansion_signal: float            # = novelty

@dataclass(frozen=True)
class PyramidResult:
    levels: tuple[PyramidLevel, ...]
    total_explained_energy: float
    final_residual: np.ndarray         # dim,  Float32
    features: PyramidFeatures
```

### `ResidualPyramid` 类签名

```python
class ResidualPyramid:
    def __init__(
        self,
        tag_rows: list[_TagVecRow],         # 复用 wave_tag_spike._TagVecRow
        *,
        max_levels: int = 3,
        top_k: int = 10,
        min_energy_ratio: float = 0.1,
        use_handshake_features: bool = True,  # D2 fallback knob: False ⇒ L1 等价
        dim: int,
    ) -> None: ...

    def analyze(self, query_vec: np.ndarray) -> PyramidResult: ...
```

不在 `__init__` 里读 DB / 拉 tag 行 — 由 caller `apply_tag_boost` 通过现有 `_load_kb_tag_vectors` 拉好后传入。这样 ResidualPyramid 是纯算法，便于单测 mock。

### `_resolve_dynamic_boost` 完整新逻辑

```python
def _resolve_dynamic_boost(
    query_vec: np.ndarray,
    settings: Settings,
    *,
    pyramid_features: PyramidFeatures | None = None,  # ★ 新参数：caller 算好传入
) -> float:
    cfg = settings.wave_phase1
    strategy = cfg.dynamic_boost_factor_strategy

    if strategy == "constant":
        return 1.0

    # strategy="epa" 走 Phase 2a 形态（不变）
    if strategy == "epa":
        try:
            from .epa_basis import basis_path
            from .epa_projector import EPAProjector
            projector = EPAProjector.from_path(basis_path(settings))
            projection = projector.project(np.asarray(query_vec, dtype=np.float32))
        except Exception:
            return 1.0
        logic_depth = max(0.0, float(projection.get("logicDepth", 0.0)))
        return max(cfg.epa_floor, logic_depth * cfg.epa_logic_depth_scale)

    # strategy="pyramid" 走完整公式
    if strategy == "pyramid":
        try:
            from .epa_basis import basis_path
            from .epa_projector import EPAProjector
            projector = EPAProjector.from_path(basis_path(settings))
            projection = projector.project(np.asarray(query_vec, dtype=np.float32))
        except Exception:
            return 1.0  # EPA 不可用 → 等价 constant
        logic_depth = max(0.0, float(projection.get("logicDepth", 0.0)))
        entropy = max(0.0, min(1.0, float(projection.get("entropy", 0.0))))  # normalized_entropy
        resonance = 0.0  # stub by D3
        # 完整公式
        if pyramid_features is None:
            tag_memo_activation = 0.0  # pyramid empty fallback
        else:
            tag_memo_activation = max(0.0, min(1.0, pyramid_features.tag_memo_activation))
        act_mult = cfg.activation_multiplier_min + tag_memo_activation * (
            cfg.activation_multiplier_max - cfg.activation_multiplier_min
        )
        resonance_term = math.log(1.0 + resonance)            # = 0 with stub
        dynamic_factor = (logic_depth * (1.0 + resonance_term) / (1.0 + entropy * 0.5)) * act_mult
        # D4 后置兜底：再乘 epa_logic_depth_scale，再 max(epa_floor, ...)
        scaled = dynamic_factor * cfg.epa_logic_depth_scale
        return max(cfg.epa_floor, scaled)

    return 1.0
```

### `apply_tag_boost` 改造

新增 strategy="pyramid" 分支，在现有 `_select_seeds` 之前 / 替代位置：

```python
# 原逻辑（strategy in {constant, epa}）：
seeds_with_sim = _select_seeds(query_vec, tag_rows, top_k=cfg.seed_top_k, ...)

# 新逻辑：
strategy = cfg.dynamic_boost_factor_strategy
pyramid_result: PyramidResult | None = None

if strategy == "pyramid":
    try:
        pyramid = ResidualPyramid(
            tag_rows,
            max_levels=cfg.pyramid_max_levels,
            top_k=cfg.pyramid_top_k,
            min_energy_ratio=cfg.pyramid_min_energy_ratio,
            use_handshake_features=cfg.pyramid_use_handshake_features,
            dim=expected_dim,
        )
        pyramid_result = pyramid.analyze(query_vec)
    except Exception:
        pyramid_result = None  # fallback 到 cosine 路径

if pyramid_result and pyramid_result.levels:
    # 用 pyramid levels[*].tags 收集 candidates，每级带 layer_decay
    candidates_with_weight: list[tuple[_TagVecRow, float]] = []
    seen: set[int] = set()
    for level in pyramid_result.levels:
        layer_decay = cfg.pyramid_layer_decay_base ** level.level   # 0.7^level
        for ptag in level.tags:
            if ptag.tag_id in seen or ptag.tag_id not in rows_by_id:
                continue
            seen.add(ptag.tag_id)
            adjusted_weight = ptag.contribution * layer_decay
            if adjusted_weight <= 0:
                continue
            candidates_with_weight.append((rows_by_id[ptag.tag_id], adjusted_weight))
    seeds_with_sim = candidates_with_weight  # 后续 spike + dedup + context 不变
else:
    # fallback 到 cosine 路径
    seeds_with_sim = _select_seeds(...)

# 后续 spike propagation / dedup / context vec 不变
# 但 _resolve_dynamic_boost 多传一个 pyramid_features：
dynamic = _resolve_dynamic_boost(
    query_vec, settings,
    pyramid_features=pyramid_result.features if pyramid_result else None,
)
```

### Config 新字段

```python
class WavePhase1Config(BaseModel):
    ...
    dynamic_boost_factor_strategy: Literal["constant", "epa", "pyramid"] = "constant"  # ★ 扩枚举
    ...  # epa_logic_depth_scale / epa_floor 保留（D4）
    # Phase 2b-1 新增：
    pyramid_max_levels: int = Field(default=3, ge=1, le=10)
    pyramid_top_k: int = Field(default=10, ge=1, le=100)
    pyramid_min_energy_ratio: float = Field(default=0.1, gt=0.0, le=1.0)
    pyramid_layer_decay_base: float = Field(default=0.7, gt=0.0, le=1.0)
    pyramid_use_handshake_features: bool = Field(default=True)
    activation_multiplier_min: float = Field(default=0.5, ge=0.0)
    activation_multiplier_max: float = Field(default=1.5, ge=0.0)
```

`config.yaml` 同步加这 7 个字段（其中 strategy 枚举值变了，注释写明 "constant" | "epa" | "pyramid"）。

### 观测指标

```python
# observability/metrics.py 新增
self.tag_dynamic_factor = Histogram(
    "tagmemorag_tag_dynamic_factor",
    "Dynamic boost factor (post-clamp) per tag-boost call",
    labelnames=("kb_name", "strategy"),
)
self.tag_pyramid_levels = Histogram(
    "tagmemorag_tag_pyramid_levels",
    "ResidualPyramid: number of levels actually computed",
    labelnames=("kb_name",),
    buckets=(0, 1, 2, 3, 4, 5),  # max_levels=3 + 1 buffer
)
self.tag_pyramid_explained_energy = Histogram(
    "tagmemorag_tag_pyramid_explained_energy",
    "ResidualPyramid: total_explained_energy ratio",
    labelnames=("kb_name",),
    buckets=(0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0),
)
self.tag_pyramid_features = Gauge(
    "tagmemorag_tag_pyramid_features",
    "ResidualPyramid: latest features per kb (tagMemoActivation/coverage/coherence)",
    labelnames=("kb_name", "feature"),
)

def record_tag_dynamic_factor(self, *, kb_name: str, strategy: str, value: float) -> None:
    self.tag_dynamic_factor.labels(kb_name=kb_name, strategy=strategy).observe(max(value, 0.0))

def record_tag_pyramid(self, *, kb_name: str, levels: int, explained: float, features: dict) -> None:
    self.tag_pyramid_levels.labels(kb_name=kb_name).observe(int(levels))
    self.tag_pyramid_explained_energy.labels(kb_name=kb_name).observe(max(explained, 0.0))
    for fname in ("tag_memo_activation", "coverage", "coherence"):
        if fname in features:
            self.tag_pyramid_features.labels(kb_name=kb_name, feature=fname).set(float(features[fname]))
```

## 关键算法步骤

### ResidualPyramid.analyze (基于 source-residual-pyramid.md §2)

```python
def analyze(self, query_vec: np.ndarray) -> PyramidResult:
    query = np.asarray(query_vec, dtype=np.float32)
    if query.shape != (self.dim,):
        raise ValueError(f"expected dim {self.dim}, got {query.shape}")

    original_magnitude = float(np.linalg.norm(query))
    original_energy = original_magnitude ** 2
    if original_energy < 1e-12:
        return _empty_result(self.dim)

    current_residual = query.copy()
    levels: list[PyramidLevel] = []
    total_explained = 0.0

    for level_idx in range(self.max_levels):
        # 1. 召回：top-K cosine on current_residual
        candidates = _topk_cosine(current_residual, self.tag_rows, self.top_k)
        if not candidates:
            break

        # 2. Gram-Schmidt 投影
        projection, residual, basis_coeffs = _gram_schmidt_project(
            current_residual, [c[0].vector for c in candidates]
        )

        # 3. 能量
        residual_magnitude = float(np.linalg.norm(residual))
        residual_energy = residual_magnitude ** 2
        current_energy = float(np.linalg.norm(current_residual)) ** 2
        energy_explained = max(0.0, current_energy - residual_energy) / original_energy

        # 4. Handshake：仅 level-0 计算（D2 L2 移植深度）
        if level_idx == 0 and self.use_handshake_features:
            magnitudes, directions = _compute_handshakes(query, [c[0].vector for c in candidates])
            handshake = _analyze_handshakes(magnitudes, directions, self.dim)
        else:
            handshake = None

        # 5. 组装 PyramidTag
        tags = tuple(
            PyramidTag(
                tag_id=row.tag_id,
                name=row.name,
                similarity=sim,
                contribution=float(basis_coeffs[i]),
                handshake_magnitude=float(magnitudes[i]) if level_idx == 0 and self.use_handshake_features else 0.0,
            )
            for i, (row, sim) in enumerate(candidates)
        )
        levels.append(PyramidLevel(
            level=level_idx,
            tags=tags,
            projection_magnitude=float(np.linalg.norm(projection)),
            residual_magnitude=residual_magnitude,
            residual_energy_ratio=residual_energy / original_energy,
            energy_explained=energy_explained,
            handshake_features=handshake,
        ))
        total_explained += energy_explained

        # 6. 早停：剩余能量 < min_energy_ratio
        current_residual = residual
        if (residual_energy / original_energy) < self.min_energy_ratio:
            break

    features = _extract_features(levels, total_explained)
    return PyramidResult(
        levels=tuple(levels),
        total_explained_energy=total_explained,
        final_residual=current_residual,
        features=features,
    )
```

### Modified Gram-Schmidt（数值稳定版）

```python
def _gram_schmidt_project(vector: np.ndarray, tag_vectors: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dim = vector.shape[0]
    n = len(tag_vectors)
    basis: list[np.ndarray] = []
    basis_coeffs = np.zeros(n, dtype=np.float32)

    for i, tv in enumerate(tag_vectors):
        v = np.array(tv, dtype=np.float32, copy=True)
        # 减去在已有基上的投影
        for u in basis:
            v -= np.dot(v, u) * u
        mag = float(np.linalg.norm(v))
        if mag > 1e-6:
            v = v / mag
            basis.append(v)
            # query 在新基向量上的绝对贡献
            basis_coeffs[i] = abs(float(np.dot(vector, v)))
        # else: 线性相关，basis_coeffs[i] = 0 默认

    # 总投影
    projection = np.zeros(dim, dtype=np.float32)
    for u in basis:
        projection += np.dot(vector, u) * u
    residual = vector - projection
    return projection, residual, basis_coeffs
```

### Handshake features（仅 level-0）

```python
def _compute_handshakes(query: np.ndarray, tag_vectors: list[np.ndarray]) -> tuple[list[float], list[np.ndarray]]:
    deltas = [query - tv for tv in tag_vectors]
    magnitudes = [float(np.linalg.norm(d)) for d in deltas]
    directions = []
    for d, mag in zip(deltas, magnitudes):
        if mag > 1e-9:
            directions.append(d / mag)
        else:
            directions.append(np.zeros_like(d))
    return magnitudes, directions

def _analyze_handshakes(magnitudes, directions, dim: int) -> HandshakeFeatures:
    n = len(directions)
    if n == 0:
        return HandshakeFeatures(0.0, 0.0, 0.0, 0.0)
    # 1. directionCoherence: 平均方向的长度
    avg_direction = np.mean(np.stack(directions), axis=0)
    direction_coherence = float(np.linalg.norm(avg_direction))
    # 2. patternStrength: 前 5 个两两点积绝对值的均值
    limit = min(n, 5)
    pairs = [
        abs(float(np.dot(directions[i], directions[j])))
        for i in range(limit) for j in range(i + 1, limit)
    ]
    pattern_strength = float(np.mean(pairs)) if pairs else 0.0
    novelty_signal = direction_coherence
    noise_signal = (1.0 - direction_coherence) * (1.0 - pattern_strength)
    return HandshakeFeatures(direction_coherence, pattern_strength, novelty_signal, noise_signal)
```

### features 提取

```python
def _extract_features(levels: list[PyramidLevel], total_explained: float) -> PyramidFeatures:
    if not levels:
        return PyramidFeatures(depth=0, coverage=0.0, novelty=1.0, coherence=0.0,
                               tag_memo_activation=0.0, expansion_signal=1.0)
    handshake = levels[0].handshake_features
    coverage = min(1.0, total_explained)
    coherence = handshake.pattern_strength if handshake else 0.0
    residual_ratio = 1.0 - coverage
    directional_novelty = handshake.novelty_signal if handshake else 0.0
    novelty = residual_ratio * 0.7 + directional_novelty * 0.3
    noise = handshake.noise_signal if handshake else 0.0
    return PyramidFeatures(
        depth=len(levels),
        coverage=coverage,
        novelty=novelty,
        coherence=coherence,
        tag_memo_activation=coverage * coherence * (1.0 - noise),
        expansion_signal=novelty,
    )
```

## 失败 / 降级语义

| 场景 | 行为 |
|---|---|
| `strategy="constant"`（默认） | 同 Phase 1/2a，恒等 1.0；ResidualPyramid 不实例化 |
| `strategy="epa"` | 同 Phase 2a，`max(epa_floor, logicDepth * scale)`；ResidualPyramid 不实例化 |
| `strategy="pyramid"` + EPA basis 不存在 | 整个 dynamic 退化为 1.0（等价 constant），不实例化 ResidualPyramid（避免无意义算力） |
| `strategy="pyramid"` + ResidualPyramid 实例化或 analyze 抛任何异常 | except 捕获 → `pyramid_result = None` ⇒ `seeds_with_sim` 走 `_select_seeds` cosine 路径 + `pyramid_features=None` ⇒ `tag_memo_activation=0` ⇒ `act_mult = 0.5`（最小值）⇒ dynamic 仍能算 |
| `strategy="pyramid"` + query 全零 / `originalEnergy < 1e-12` | analyze 返 empty result（levels=[], features 全 0）⇒ candidates 列表空 ⇒ `apply_tag_boost` 走 `skipped_reason="no_seeds"` 路径，返原 query_vec |
| `strategy="pyramid"` + pyramid 跑通但 levels=[]（top-k cosine 全 < 0 或 tag_rows 空） | 同上 |
| `strategy="pyramid"` + GS 全部线性相关 | basis_coeffs 全 0 ⇒ contribution 全 0 ⇒ adjusted_weight 全 0 ⇒ candidates_with_weight 空 ⇒ `skipped_reason="no_seeds"` |
| `pyramid_use_handshake_features=False` | 退到 L1 等价：handshake=None ⇒ coherence=0 + noise=0 ⇒ `tag_memo_activation = coverage * 0 * 1 = 0` ⇒ `act_mult = 0.5`（最小值）⇒ pyramid 通路退化为"只调 logicDepth/entropy" |
| `act_min == act_max`（运维误配） | `act_mult` 退化为常数；不破公式 |
| 公式分母 `1 + entropy*0.5` 永远 ≥ 1，不会除零 | — |

## 兼容性

| 维度 | 行为 |
|---|---|
| 旧 `config.yaml` 没新字段 | pydantic 默认值兜住；strategy 默认 `"constant"` ⇒ 完全等价 Phase 2a |
| `strategy="constant"`（默认） | 完全等价 Phase 2a；ResidualPyramid 不实例化；新观测指标不写入（只在 strategy != constant 时记录） |
| `strategy="epa"` | 完全等价 Phase 2a；ResidualPyramid 不实例化 |
| Phase 0 e2e baseline invariance（spike-off） | 不变 |
| 8 个 hashing eval suite（spike-on, strategy=constant） | 不变（CI 跑这条） |
| `epa_logic_depth_scale` / `epa_floor` 字段 | strategy=epa 时同 Phase 2a；strategy=pyramid 时作为后置乘子/下限（D4） |

## 回滚

```yaml
# 软回滚（不删数据）
wave_phase1:
  dynamic_boost_factor_strategy: epa      # 退到 Phase 2a 形态
  # 或更稳：
  dynamic_boost_factor_strategy: constant # 退到 Phase 1 形态
```

```yaml
# L1 退化（保留 pyramid，关 handshake）
wave_phase1:
  dynamic_boost_factor_strategy: pyramid
  pyramid_use_handshake_features: false   # tag_memo_activation 退化为 0 ⇒ act_mult 取 min
```

```bash
# 硬回滚（revert）
git revert <phase2b1-commit-range>
```

## 性能预算

- ResidualPyramid.analyze 每 query 一次，max_levels=3：每级 top-K=10 cosine + Gram-Schmidt（10 个向量正交化，dim=64..384）。规模 ≤ O(L * K * dim²) = 3 * 10 * 384² ≈ 4.4M 次乘加，单次 < 5ms。
- 每 query 一次实例化 ResidualPyramid（持有 tag_rows 引用，不复制）— `_load_kb_tag_vectors` 已有 cost；不引入额外 SQL。
- 观测指标 4 个，每次 spike-on 调用 4 次 observe + 3 次 set，纳秒级。

## Open implementation questions（implement 阶段回答）

1. **D8 候选**：strategy="pyramid" 在 hashing dim=64 / 12-tag fixture 上的 alpha 序列是否满足 D2 阈值？诊断脚本（Step 6）跑出后决定是否调 `epa_logic_depth_scale` 默认值（Phase 2a 留下的 2.0 是为 strategy=epa 校准的；strategy=pyramid 公式形态变了，可能要重调）。
2. ResidualPyramid 的实例化频率：当前设计是每 query 一次（lightweight，tag_rows 引用传递）。如果 profile 显示 `_load_kb_tag_vectors` 是瓶颈，再加 module-level cache（不在本任务范围）。
