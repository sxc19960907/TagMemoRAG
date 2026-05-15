# Design — Phase 2b-2: worldview gating + language penalty + ghost tag injection

## 目的

把 PRD 的 D1-D8 决策落到模块级契约 + 数据契约 + 关键算法步骤 + 失败语义。Phase 2b-2 是 **Moderate 任务**（API 扩字段 + wave_tag_spike 4 段调制器接通，不动算法主路径），本设计覆盖：模块边界、数据契约、关键算法步骤、失败/降级语义、兼容性、回滚。

## 模块边界

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Edge: api.py ★MOD                                                        │
│   SearchRequest                                                          │
│     + core_tags: list[str] = []                                          │
│     + ghost_tags: list[GhostTagSpec] = []                                │
│   GhostTagSpec ★ NEW                                                     │
│     {name: str, vector: list[float], is_core: bool = False}              │
│   /search 路由把字段透传到 execute_search                                 │
└──────────────────┬───────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────────────────────────┐
│ search_runtime.execute_search ★MOD                                       │
│   + core_tags: Sequence[str] = ()                                        │
│   + ghost_tags: Sequence[GhostTag] = ()                                  │
│   把这两个透传给 apply_tag_boost                                          │
└──────────────────┬───────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────────────────────────┐
│ wave_tag_spike ★MOD                                                      │
│   apply_tag_boost(..., core_tags=(), ghost_tags=())                      │
│     ├─ 入口处 resolve core_tags（synonym → canonical, dedup, drop空）    │
│     ├─ strategy="pyramid" 路径下                                         │
│     │   ├─ candidate 收集 weight × langPenalty × coreBoost               │
│     │   ├─ merge 之后插入 _inject_core_completion                        │
│     │   └─ 之后插入 _inject_ghosts                                       │
│     ├─ strategy ∈ {"constant", "epa"} 路径下                             │
│     │   └─ 仍走 _select_seeds，core/ghost/lang 不生效（保持 R10）         │
│   _resolve_core_boost_factor(query_vec, settings, pyramid_features)      │
│     → returns dynamicCoreBoostFactor (1.20..1.40)                        │
│   _compute_lang_penalty(tag_name, query_world, settings)                 │
│     → returns penalty multiplier (1.0 if disabled or not triggered)      │
│   _inject_core_completion(candidates, core_canonical, kb_name, settings) │
│     → 从 SQL 查 missing tags，注入 maxBaseWeight × dynamicCoreBoostFactor│
│   _inject_ghosts(candidates, ghost_tags, expected_dim, info)             │
│     → 负数 id + dim 校验 + maxBaseWeight × (dynamicCore if isCore else 1)│
│   ★ TagBoostInfo 扩字段：                                                 │
│     + core_tags_input: tuple[str, ...]                                   │
│     + core_tags_resolved: tuple[str, ...]                                │
│     + core_completion_count: int                                         │
│     + ghosts_injected: int                                               │
│     + ghost_skipped_dim_mismatch: int                                    │
│     + lang_penalty_applied_count: int                                    │
│     + query_world: str                                                   │
└──────────────────┬───────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────────────────────────┐
│ tag_governance.resolve_tag_for_kb (existing) ★ READ                      │
│   按 (kb_name, raw_tag) → canonical name 字符串                          │
└──────────────────┬───────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────────────────────────┐
│ Config ★MOD                                                              │
│   wave_phase1.lang_penalty_enabled: bool = False                         │
│   wave_phase1.lang_penalty_unknown: float = 0.4                          │
│   wave_phase1.lang_penalty_cross_domain: float = 0.3                     │
│   wave_phase1.core_boost_min: float = 1.20                               │
│   wave_phase1.core_boost_max: float = 1.40                               │
└──────────────────┬───────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────────────────────────┐
│ Observability ★MOD                                                       │
│   + tag_lang_penalty_applied: Counter(kb_name, query_world_kind)         │
│   + tag_core_tags_resolved: Histogram(kb_name)                           │
│   + tag_ghosts_injected: Histogram(kb_name, kind)                        │
└──────────────────────────────────────────────────────────────────────────┘
```

## 数据契约

### `wave_tag_spike` 新数据结构

```python
@dataclass(frozen=True)
class GhostTag:
    """Caller-supplied tag with explicit vector, bypassing KB."""
    name: str
    vector: np.ndarray         # shape (dim,)
    is_core: bool = False

@dataclass(frozen=True)
class _ResolvedCoreSet:
    """Internal — synonym-resolved + dedup'd core tag canonical names."""
    input_raw: tuple[str, ...]
    canonical: tuple[str, ...]   # post-resolve, post-dedup, lowercase

@dataclass(frozen=True)
class TagBoostInfo:
    # ... 现有字段 ...
    # Phase 2b-2 新增：
    core_tags_input: tuple[str, ...] = ()
    core_tags_resolved: tuple[str, ...] = ()
    core_completion_count: int = 0
    ghosts_injected: int = 0
    ghost_skipped_dim_mismatch: int = 0
    lang_penalty_applied_count: int = 0
    query_world: str = ""
```

### `apply_tag_boost` 签名扩展

```python
def apply_tag_boost(
    query_vec: np.ndarray,
    *,
    kb_name: str,
    settings: Settings,
    base_tag_boost: float,
    core_tags: Sequence[str] = (),
    ghost_tags: Sequence[GhostTag] = (),
) -> tuple[np.ndarray, TagBoostInfo]: ...
```

### `SearchRequest` / `GhostTagSpec` 扩展

```python
class GhostTagSpec(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    vector: list[float] = Field(..., min_length=1)
    is_core: bool = False

class SearchRequest(BaseModel):
    # ... 现有字段 ...
    core_tags: list[str] = Field(default_factory=list)
    ghost_tags: list[GhostTagSpec] = Field(default_factory=list)
```

## 关键算法步骤

### 入口处 resolve core_tags（apply_tag_boost 第一步）

```python
def _resolve_core_tag_set(
    raw: Sequence[str], *, kb_name: str, settings: Settings
) -> _ResolvedCoreSet:
    cleaned: list[str] = []
    seen: set[str] = set()
    for t in raw:
        if not isinstance(t, str):
            continue
        s = t.strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        cleaned.append(s)

    canonical: list[str] = []
    canonical_seen: set[str] = set()
    for raw_lower in cleaned:
        try:
            resolution = tag_governance.resolve_tag_for_kb(
                raw_lower, kb_name=kb_name, settings=settings,
            )
            target = (resolution.canonical_tag or resolution.tag or raw_lower).strip().lower()
        except Exception:
            target = raw_lower
        if target not in canonical_seen:
            canonical_seen.add(target)
            canonical.append(target)
    return _ResolvedCoreSet(input_raw=tuple(cleaned), canonical=tuple(canonical))
```

> **Note**：`tag_governance.resolve_tag_for_kb` 接口 — 设计阶段假定它存在或写一个轻量包装；implement 阶段如果 governance 模块只暴露 `resolve_tag(tag, policy)` 风格 API，就在 `wave_tag_spike` 内部 lazy-load policy（`_load_kb_policy(kb_name, settings)`，缓存）。

### dynamicCoreBoostFactor + coreBoost 公式

```python
def _resolve_core_boost_factor(
    query_vec: np.ndarray,
    settings: Settings,
    *,
    pyramid_features: PyramidFeatures | None = None,
) -> float:
    """Source TagMemoEngine.js:96-98."""
    cfg = settings.wave_phase1
    # 复用 _resolve_dynamic_boost 内部 EPA project 的 logicDepth / coverage
    logic_depth = 0.0
    try:
        from .epa_basis import basis_path
        from .epa_projector import EPAProjector
        projector = EPAProjector.from_path(basis_path(settings))
        proj = projector.project(np.asarray(query_vec, dtype=np.float32))
        logic_depth = max(0.0, float(proj.get("logicDepth", 0.0)))
    except Exception:
        pass
    coverage = float(pyramid_features.coverage) if pyramid_features is not None else 0.0
    core_metric = 0.5 * logic_depth + 0.5 * (1.0 - coverage)
    cmin = float(cfg.core_boost_min)
    cmax = float(cfg.core_boost_max)
    return cmin + max(0.0, min(1.0, core_metric)) * (cmax - cmin)


def _per_tag_core_boost(is_core: bool, individual_relevance: float, dynamic_core: float) -> float:
    """Source TagMemoEngine.js:144-145."""
    if not is_core:
        return 1.0
    rel = max(0.0, min(1.0, float(individual_relevance)))
    return dynamic_core * (0.95 + rel * 0.10)
```

### langPenalty 实装

```python
_TECH_TAG_PATTERN = re.compile(r"^[A-Za-z0-9\-_.\s]+$")
_TECH_WORLD_PATTERN = re.compile(r"^[A-Za-z0-9\-_.]+$")
_SOCIAL_WORLD_PATTERN = re.compile(r"Politics|Society|History|Economics|Culture", re.IGNORECASE)
_CJK_PATTERN = re.compile(r"[一-龥]")


def _compute_lang_penalty(
    tag_name: str,
    query_world: str,
    settings: Settings,
) -> tuple[float, str]:
    """Returns (penalty_multiplier, query_world_kind).

    query_world_kind ∈ {disabled, technical, unknown, social, cross_domain_other}.
    """
    cfg = settings.wave_phase1
    if not cfg.lang_penalty_enabled:
        return 1.0, "disabled"
    name = tag_name or ""
    is_tech_noise = (
        not _CJK_PATTERN.search(name)
        and bool(_TECH_TAG_PATTERN.match(name))
        and len(name) > 3
    )
    qw = query_world or "Unknown"
    is_tech_world = qw != "Unknown" and bool(_TECH_WORLD_PATTERN.match(qw))
    if is_tech_world:
        return 1.0, "technical"
    if not is_tech_noise:
        return 1.0, ("unknown" if qw == "Unknown" else "cross_domain_other")
    base = float(cfg.lang_penalty_unknown if qw == "Unknown" else cfg.lang_penalty_cross_domain)
    if _SOCIAL_WORLD_PATTERN.search(qw):
        return math.sqrt(base), "social"
    return base, ("unknown" if qw == "Unknown" else "cross_domain_other")
```

### Pyramid candidates 修饰

```python
# 替换 Phase 2b-1 的 candidates_with_weight 收集（src/tagmemorag/wave_tag_spike.py:418-430）
seen_tag_ids: set[int] = set()
candidates_with_weight: list[tuple[_TagVecRow, float, bool]] = []  # (row, weight, is_core)
core_canonical_set = set(resolved_core.canonical)
dynamic_core = _resolve_core_boost_factor(query_vec, settings, pyramid_features=pyramid_result.features)
lang_applied = 0
for level in pyramid_result.levels:
    decay = layer_decay_base ** int(level.level)
    for ptag in level.tags:
        if ptag.tag_id in seen_tag_ids:
            continue
        row = rows_by_id_seed.get(ptag.tag_id)
        if row is None:
            continue
        is_core = row.name.lower() in core_canonical_set
        core_boost = _per_tag_core_boost(is_core, ptag.similarity, dynamic_core)
        lang_pen, world_kind = _compute_lang_penalty(row.name, query_world, settings)
        if lang_pen < 1.0:
            lang_applied += 1
            metrics.tag_lang_penalty_applied.labels(kb_name=kb_name, query_world_kind=world_kind).inc()
        weight = float(ptag.contribution) * decay * lang_pen * core_boost
        if weight <= 0.0:
            continue
        seen_tag_ids.add(ptag.tag_id)
        candidates_with_weight.append((row, weight, is_core))
```

### Core completion

```python
def _inject_core_completion(
    *,
    existing: list[tuple[_TagVecRow, float, bool]],
    canonical_core: Sequence[str],
    kb_name: str,
    settings: Settings,
    expected_dim: int,
    dynamic_core: float,
) -> tuple[list[tuple[_TagVecRow, float, bool]], int]:
    """Source TagMemoEngine.js:312-342.

    Pull missing core tags from SQL and inject with maxBaseWeight × dynamic_core.
    Returns (extended_list, count_added).
    """
    if not canonical_core:
        return existing, 0
    seen_lower = {row.name.lower() for row, _w, _c in existing}
    missing = [c for c in canonical_core if c not in seen_lower]
    if not missing:
        return existing, 0
    if existing:
        max_base = max((w / dynamic_core if dynamic_core > 1e-9 else w) for _r, w, _c in existing)
    else:
        max_base = 1.0
    rows = _load_kb_tag_vectors_by_names(settings, kb_name, missing, expected_dim)
    added: list[tuple[_TagVecRow, float, bool]] = []
    for row in rows:
        if row.name.lower() not in seen_lower:
            seen_lower.add(row.name.lower())
            added.append((row, max_base * dynamic_core, True))
    return existing + added, len(added)
```

`_load_kb_tag_vectors_by_names` = 模仿 `_load_kb_tag_vectors`（已在 wave_tag_spike.py:234-245）但加 `WHERE name IN (?,?)` filter；只取 `embedding_dim == expected_dim` 的行。

### Ghost injection

```python
def _inject_ghosts(
    *,
    existing: list[tuple[_TagVecRow, float, bool]],
    ghosts: Sequence[GhostTag],
    expected_dim: int,
    dynamic_core: float,
) -> tuple[list[tuple[_TagVecRow, float, bool]], int, int]:
    """Source TagMemoEngine.js:344-372.

    Returns (extended_list, injected_count, dim_mismatch_count).
    """
    if not ghosts:
        return existing, 0, 0
    if existing:
        max_base = max((w / dynamic_core if dynamic_core > 1e-9 else w) for _r, w, _c in existing)
    else:
        max_base = 1.0
    out = list(existing)
    next_id = -1
    injected = 0
    skipped_dim = 0
    for ghost in ghosts:
        vec = np.asarray(ghost.vector, dtype=np.float32)
        if vec.shape != (expected_dim,):
            skipped_dim += 1
            continue
        weight = max_base * (dynamic_core if ghost.is_core else 1.0)
        ghost_row = _TagVecRow(tag_id=next_id, name=str(ghost.name), vector=vec)
        next_id -= 1
        out.append((ghost_row, weight, bool(ghost.is_core)))
        injected += 1
    return out, injected, skipped_dim
```

### apply_tag_boost 主路径骨架（diff vs Phase 2b-1）

```python
# 入口处：
resolved_core = _resolve_core_tag_set(core_tags, kb_name=kb_name, settings=settings)
query_world = ""
if pyramid_result is not None:
    # extract dominant axis from EPAProjector — or pass through from somewhere
    try:
        proj = EPAProjector.from_path(basis_path(settings)).project(query_vec)
        domain_axes = proj.get("dominantAxes", [])
        if domain_axes:
            query_world = str(domain_axes[0].get("label") or "Unknown")
        else:
            query_world = "Unknown"
    except Exception:
        query_world = "Unknown"

# pyramid candidates 收集时用 lang/core boost 修饰（如上）

# After spike merge (existing seed_entries + emergent_entries):
candidates_tuples = [(row, weight, False) for row, weight in candidates]  # 现有路径

# Strategy="pyramid" only: 补 core completion + ghost injection
if strategy == "pyramid":
    candidates_tuples, completion_count = _inject_core_completion(
        existing=candidates_tuples,
        canonical_core=resolved_core.canonical,
        kb_name=kb_name, settings=settings, expected_dim=expected_dim,
        dynamic_core=dynamic_core_factor,
    )
    candidates_tuples, ghost_injected, ghost_dim_skip = _inject_ghosts(
        existing=candidates_tuples,
        ghosts=ghost_tags,
        expected_dim=expected_dim,
        dynamic_core=dynamic_core_factor,
    )
else:
    completion_count = 0
    ghost_injected = 0
    ghost_dim_skip = 0

# Existing dedup / context vector / fuse 路径不变（接受 (row, weight) tuple，is_core 仅记录到 info，不影响 weight）。
candidates = [(row, w) for row, w, _ic in candidates_tuples]
```

## 失败 / 降级语义

| 场景 | 行为 |
|---|---|
| `core_tags=[]` 且 `ghost_tags=[]` 且 `lang_penalty_enabled=False`（默认） | strategy="pyramid" 完全等价 Phase 2b-1；其他 strategy 不变 |
| `core_tags` 含未知 tag（不在 canonical / synonym） | 保留原字符串走 core completion 路径；DB 查 `WHERE name=?` 仍可能命中（拼写差异）；查不到 ⇒ 静默 skip + metric 计数 |
| `ghost_tags` 含 dim mismatch | skip 该 ghost，info.ghost_skipped_dim_mismatch++，metric kind="skipped_dim" |
| `ghost_tags` 含空 name | skip 该 ghost（视为 dim mismatch 类） |
| EPA basis 不可用 ⇒ logicDepth=0 / coverage=0 | dynamic_core_factor = core_boost_min（1.20，下限）；query_world="Unknown" ⇒ 进 langPenalty 的 unknown 分支 |
| query 全零 / pyramid empty | Phase 2b-1 已有 fallback 到 `_select_seeds`；strategy != pyramid 路径下 core/ghost 不生效（fallback 已经退出 pyramid 路径） |
| `tag_governance` resolve 抛异常 | except 捕获 ⇒ 用原 raw_lower 当 canonical（保守）；不破搜索 |
| `_load_kb_tag_vectors_by_names` SQL 失败 | except 捕获 ⇒ core completion 返回空 added，info.core_completion_count=0；不破搜索 |
| candidates 为空 + 全部走 ghost injection | maxBaseWeight=1.0，ghost 仍可注入；alpha 仍能算（但 effective_boost 会很小） |
| strategy != pyramid 路径下 caller 仍传 core_tags / ghost_tags | core_tags / ghost_tags 字段记录到 TagBoostInfo（input_raw / resolved），但**不影响 weight 公式**；PRD R10 锁住 |

## 兼容性

| 维度 | 行为 |
|---|---|
| 旧 caller（不传 core_tags / ghost_tags） | pydantic 默认 `[]`；行为完全不变 |
| 旧 `config.yaml` 没新字段 | pydantic 默认值 `lang_penalty_enabled=False` 等 ⇒ 等价 Phase 2b-1 |
| `strategy="constant"` 默认 | 完全等价 Phase 2b-1（不进 pyramid 路径，core/ghost/lang 全不生效） |
| `strategy="epa"` | 同上 |
| `strategy="pyramid"` + 默认参数 + 不传 core/ghost | 完全等价 Phase 2b-1（langPenalty=disabled ⇒ 1.0；coreBoost=1.0；core completion / ghost injection 空） |
| Phase 0 e2e baseline invariance（spike-off） | 不变 |
| 8 个 hashing eval suite（spike-on, strategy=constant） | 不变（CI 跑这条） |

## 回滚

```yaml
# 软回滚（不删数据）
wave_phase1:
  lang_penalty_enabled: false   # 关 langPenalty（也是默认）
  # 或更彻底：
  dynamic_boost_factor_strategy: epa     # 退到 Phase 2a 形态
  dynamic_boost_factor_strategy: constant  # 退到 Phase 1 形态
```

API 侧：caller 不传 core_tags / ghost_tags 即可。

```bash
# 硬回滚
git revert <phase2b2-commit-range>
```

## 性能预算

- `_compute_lang_penalty` 每个 candidate 调用一次：4 个 regex match，纳秒级。
- `_resolve_core_boost_factor` 每 query 一次（已有 EPA project 一次的 cost；增量 ~微秒）。
- `_inject_core_completion` SQL 命中索引（`UNIQUE(kb_name, name)`），最多 N=core_tags 行。
- `_inject_ghosts` 纯内存，N=ghost_tags 行。
- 观测指标 3 个，每次 spike-on 调用最多 inc 一次 + observe 两次。

总开销 ~ < 1ms 增量（在 strategy=pyramid 路径下）。

## 测试策略

### 新增 `tests/unit/test_apply_tag_boost_modulators.py`（≥10 段）

- `test_resolve_core_tag_set_dedup_and_lowercase`
- `test_resolve_core_tag_set_resolves_synonym_to_canonical`
- `test_resolve_core_tag_set_unknown_tag_passes_through`
- `test_compute_lang_penalty_disabled_returns_one`
- `test_compute_lang_penalty_technical_world_returns_one`
- `test_compute_lang_penalty_unknown_world_with_tech_tag`
- `test_compute_lang_penalty_social_world_softens_via_sqrt`
- `test_compute_lang_penalty_chinese_tag_never_penalized`
- `test_resolve_core_boost_factor_formula_at_extremes`
- `test_per_tag_core_boost_individual_relevance`
- `test_inject_core_completion_pulls_missing_from_db`
- `test_inject_ghosts_dim_mismatch_skipped`
- `test_inject_ghosts_negative_id_does_not_collide`

### 现有 `tests/unit/test_apply_tag_boost.py` 加 ≥3 段

- `test_apply_tag_boost_core_tags_recorded_in_info`
- `test_apply_tag_boost_ghost_tags_appear_in_matched_names`
- `test_apply_tag_boost_constant_strategy_ignores_core_ghost`（R10 锁底）

### `tests/unit/test_observability_metrics.py` 加 ≥1 段

- `test_phase2b2_modulator_metrics_register_custom_series`

## Open implementation questions

1. **tag_governance API 形态**：implement 阶段先看 `tag_governance.resolve_tag_for_kb` 是否已存在；若没有，写一个 thin wrapper：`resolve_canonical(kb_name, raw_tag, settings) -> str`，内部 lazy-load policy 并缓存。
2. **query_world 提取放哪**：当前设计在 `apply_tag_boost` 里二次调 `EPAProjector.project()`（`_resolve_dynamic_boost` 已经调一次）；为避免重复 IO，implement 阶段把第一次 project 结果缓存到一个 local dict 传下去，或重构 `_resolve_dynamic_boost` 返回 `(dynamic, query_world)` tuple。**推荐**：重构 `_resolve_dynamic_boost` 返回 `_DynamicBoostResult(dynamic=float, query_world=str)`。
3. **candidates triple 改造范围**：现有 `seed_entries + emergent_entries` 是 `(row, weight)` tuple；改成 `(row, weight, is_core)` triple 的扩散范围只在 `apply_tag_boost` 函数内部，dedup / context 入口处再砍回 tuple。implement 阶段确认。
