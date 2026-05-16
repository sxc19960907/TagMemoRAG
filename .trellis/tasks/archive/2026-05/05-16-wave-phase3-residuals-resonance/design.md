# Design — Phase 3：detectCrossDomainResonance

## 目的

把 PRD 的 D1-D6 决策落到模块级契约 + 数据契约 + 关键算法步骤 + 失败语义。Phase 3 是 **Moderate 任务**（1 helper + 接通 + 测试 + 文档），覆盖：模块边界、数据契约、关键算法步骤、失败/降级语义、兼容性、回滚。

## 模块边界

```
┌──────────────────────────────────────────────────────────────────────────┐
│ wave_tag_spike ★MOD                                                      │
│   detect_cross_domain_resonance(dominant_axes)                           │
│     → (resonance: float, bridges: list[dict])                            │
│   _resolve_dynamic_boost_with_world(...) ★MOD                            │
│     ├─ 默认（cross_domain_resonance_enabled=False）：resonance=0 不变     │
│     └─ enabled=True：调 detect_cross_domain_resonance(projection["dominantAxes"])│
│   apply_tag_boost(...) ★MOD                                              │
│     ├─ 入口处 EPA project（已有）+ resonance 计算（新增 一次性）          │
│     ├─ 把 resonance + len(bridges) 记录到 info_extra                      │
│     └─ 把 bridges list 传给 search_debug_payload（仅当 enabled=true）     │
│   ★ TagBoostInfo 扩 2 字段：                                              │
│     + cross_domain_resonance: float = 0.0                                │
│     + cross_domain_bridges_count: int = 0                                │
└──────────────────┬───────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────────────────────────┐
│ search_runtime ★MOD                                                      │
│   search_debug_payload                                                   │
│     `tag_boost_debug.cross_domain_bridges: list[dict]`                   │
└──────────────────┬───────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────────────────────────┐
│ Config ★MOD                                                              │
│   wave_phase1.cross_domain_resonance_enabled: bool = False               │
└──────────────────┬───────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────────────────────────┐
│ Observability ★MOD                                                       │
│   + tag_resonance_value: Histogram(kb_name)                              │
│   + tag_resonance_bridges_count: Histogram(kb_name)                      │
└──────────────────────────────────────────────────────────────────────────┘
```

## 数据契约

### `wave_tag_spike` 新 helper

```python
_RESONANCE_CO_ACTIVATION_THRESHOLD = 0.15  # V6 EPAModule.js:186 hardcode


def detect_cross_domain_resonance(
    dominant_axes: Sequence[Mapping[str, object]],
) -> tuple[float, list[dict]]:
    """V6 detectCrossDomainResonance port.

    Source: lioensky/VCPToolBox EPAModule.js:170-201 (commit aff66193).
    Computes co-activation strength (sqrt(top.energy * sec.energy)) for each
    secondary axis paired with the top axis; entries above 0.15 form "bridges".
    Total resonance = sum of bridge strengths.

    Args:
        dominant_axes: list of {"label": str, "energy": float, "index": int,
                                 "projection": float}, desc-sorted by energy.
                       Output of `EPAProjector.project()["dominantAxes"]`.

    Returns:
        (resonance_total, bridges) where:
          - resonance_total: scalar fed to dynamicBoostFactor as log(1+resonance)
          - bridges: list of {from, to, strength, balance} dicts (diagnostics only)
    """
    if len(dominant_axes) < 2:
        return 0.0, []
    top = dominant_axes[0]
    top_energy = float(top.get("energy", 0.0))
    top_label = str(top.get("label", ""))
    bridges: list[dict] = []
    for sec in dominant_axes[1:]:
        sec_energy = float(sec.get("energy", 0.0))
        co_act = math.sqrt(max(0.0, top_energy * sec_energy))
        if co_act > _RESONANCE_CO_ACTIVATION_THRESHOLD:
            sec_label = str(sec.get("label", ""))
            balance = (
                min(top_energy, sec_energy) / max(top_energy, sec_energy)
                if max(top_energy, sec_energy) > 1e-12
                else 0.0
            )
            bridges.append({
                "from": top_label,
                "to": sec_label,
                "strength": co_act,
                "balance": balance,
            })
    return sum(float(b["strength"]) for b in bridges), bridges
```

### `_DynamicBoostResult` 扩展

```python
@dataclass(frozen=True)
class _DynamicBoostResult:
    dynamic: float
    query_world: str
    # Phase 3 新增：
    resonance: float = 0.0
    bridges: tuple[dict, ...] = ()
```

### `TagBoostInfo` 扩 2 字段

```python
@dataclass(frozen=True)
class TagBoostInfo:
    # ... 现有字段 ...
    # Phase 3 新增：
    cross_domain_resonance: float = 0.0
    cross_domain_bridges_count: int = 0
```

`to_dict` 同步加 `cross_domain_resonance / cross_domain_bridges_count`。

### `WavePhase1Config` 扩 1 字段

```python
cross_domain_resonance_enabled: bool = False
```

`config.yaml` 同步。

## 关键算法步骤

### `_resolve_dynamic_boost_with_world` 接通

```python
# Phase 2b-1 末态（src/tagmemorag/wave_tag_spike.py:790-803）：
#   resonance = 0.0
#   resonance_term = math.log(1.0 + resonance)  ⇒ 0
#   dynamic = (logic_depth * (1 + resonance_term) / (1 + entropy*0.5)) * activation_mult
#           * post_scale  (floored at floor)

# Phase 3 接通：
resonance = 0.0
bridges: list[dict] = []
if cfg.cross_domain_resonance_enabled:
    dominant = projection.get("dominantAxes") or []
    resonance, bridges = detect_cross_domain_resonance(dominant)
resonance_term = math.log(1.0 + max(0.0, resonance))
# ... 其余不变 ...

return _DynamicBoostResult(
    dynamic=max(floor, dynamic * post_scale),
    query_world=query_world,
    resonance=float(resonance),
    bridges=tuple(bridges),
)
```

### `apply_tag_boost` 出口写 info

```python
# 现有 boost_with_world = _resolve_dynamic_boost_with_world(...)
# 在 info_extra 里加：
info_extra["cross_domain_resonance"] = float(boost_with_world.resonance)
info_extra["cross_domain_bridges_count"] = len(boost_with_world.bridges)
```

### Metric 上报

```python
# 在 apply_tag_boost 出口（与 record_tag_dynamic_factor 同处）：
if cfg.cross_domain_resonance_enabled:
    metrics.record_tag_resonance_value(
        kb_name=kb_name, value=float(boost_with_world.resonance)
    )
    metrics.record_tag_resonance_bridges_count(
        kb_name=kb_name, count=len(boost_with_world.bridges)
    )
```

### search_debug_payload 暴露 bridges

```python
# search_runtime.search_debug_payload 现有：
# if execution.tag_boost_info is not None:
#     payload["tag_boost"] = execution.tag_boost_info.to_dict()
# 加：
if execution.tag_boost_info is not None and execution.tag_boost_bridges:
    payload["tag_boost_debug"] = {"cross_domain_bridges": list(execution.tag_boost_bridges)}
```

但 SearchExecution 现在没有 `tag_boost_bridges` 字段 — 加：

```python
@dataclass(frozen=True)
class SearchExecution:
    # ... 现有 ...
    tag_boost_bridges: tuple[dict, ...] = ()
```

`execute_search` 把 boost_with_world.bridges 串起来。

## 失败 / 降级语义

| 场景 | 行为 |
|---|---|
| `cross_domain_resonance_enabled=False`（默认） | 完全等价 Phase 2b-1；resonance=0 不接公式；info 字段 = 默认 0 |
| EPA basis 不可用 / `project()` 抛 | 现有 `_resolve_dynamic_boost_with_world` 已 except → return constant；本任务接入点位于 except 分支之后，不会被走到 |
| `dominantAxes` 长度 < 2（cold-start basis K=1, 或聚焦 query） | resonance=0；bridges=[]；与 stub 等价 |
| `dominantAxes` 含格式异常（缺 "energy" 字段） | `float(top.get("energy", 0.0))` ⇒ 0；resonance 退化为 0 |
| `top.energy` 或 `sec.energy` 为负 / NaN | `max(0.0, top * sec)` 防负；NaN 通过 sqrt 传导 ⇒ 算法上由 EPAProjector 保证非负，本层不另加防 |
| `metrics.record_tag_resonance_*` 调用前 NoopMetrics | 自动 noop（现有 `__getattr__` pattern） |

## 兼容性

| 维度 | 行为 |
|---|---|
| 旧 caller（不传 cross_domain_resonance_enabled） | pydantic 默认 false；行为完全不变 |
| 旧 `config.yaml` 没新字段 | 默认 false ⇒ 等价 Phase 2b-2 |
| `strategy="constant"` 默认 | 完全等价（不进 pyramid 路径，resonance 不算） |
| `strategy="epa"` | 等价（不进 pyramid 路径） |
| `strategy="pyramid"` + 默认 enabled=false | 完全等价 Phase 2b-1（resonance=0 不变） |
| Phase 0 e2e baseline invariance（spike-off） | 不变 |
| 8 个 hashing eval suite（spike-on, strategy=constant） | 不变（CI 跑这条；resonance_enabled 默认 false） |
| `strategy="pyramid"` + enabled=true | **可能漂**（公式输出变），但 D2 阈值仍 PASS（必要时重 calibrate `pyramid_post_scale`）|

## 回滚

```yaml
# 软回滚（不删数据）
wave_phase1:
  cross_domain_resonance_enabled: false   # 关 resonance（默认）
```

```bash
# 硬回滚
git revert <phase3-commit>
```

## 性能预算

- `detect_cross_domain_resonance`：O(K)，K ≤ 10 ⇒ 纳秒级。
- 1 次 EPA project 已是 Phase 2b-1 末态成本；本任务**不增加 EPA IO**（dominantAxes 来自现有 `_resolve_dynamic_boost_with_world` 内的 project 结果）。
- 2 个 metric observe + 1 次 list[dict] 构造 + 1 次 tuple 化 ⇒ < 10 µs。

总开销 ~ < 0.1 ms 增量。

## 测试策略

### 新增 `tests/unit/test_cross_domain_resonance.py`（≥6 段）

- `test_resonance_dominant_axes_empty_returns_zero`
- `test_resonance_dominant_axes_single_returns_zero`
- `test_resonance_below_threshold_excluded`（`top=0.5, sec=0.04` ⇒ co_act≈0.141<0.15 ⇒ 0）
- `test_resonance_single_bridge`（`top=0.5, sec=0.5` ⇒ resonance=0.5；balance=1.0）
- `test_resonance_multiple_bridges_sum_correctly`（3 axes [0.5, 0.4, 0.3] ⇒ resonance≈0.834）
- `test_resonance_balance_extremes`（`top=0.9, sec=0.1` ⇒ co_act=0.3 > 0.15；balance=0.111）
- `test_resonance_handles_missing_energy_field`（dominant_axes 缺 energy ⇒ 0；不抛）

### 现有 `tests/unit/test_apply_tag_boost.py` 加 ≥1 段

- `test_apply_tag_boost_resonance_disabled_default`：`enabled=false` ⇒ info.cross_domain_resonance=0.0；fused 输出与 Phase 2b-1 完全一致

### 现有 `tests/unit/test_epa_logic_depth.py` 加 ≥1 段

- `test_pyramid_dynamic_boost_with_resonance_enabled_extends_factor`：mock dominantAxes 给定 ⇒ dynamic factor 比 disabled 路径大 `(1 + log(1+resonance))` 倍

### 现有 `tests/unit/test_observability_metrics.py` 加 1 段

- `test_phase3_resonance_metrics_register_custom_series`

## Open implementation questions

1. **diag 重 calibrate**：implement.md Step 7 跑一次 diag enabled=true。如果 D2 阈值 fail ⇒ sweep `pyramid_post_scale` ∈ {1.0, 2.0, 3.0, 4.0, 5.0, 6.0} 找最小 PASS。如 PASS ⇒ 不动 default 4.0。
2. **bridges 在 SearchExecution 字段**：是否进 `tag_boost_info` 还是单独 `tag_boost_bridges` 字段？设计选**单独字段**，避免 to_dict 面包扩张。implement 阶段如果发现 search_runtime 现有结构不便加，回退到把 bridges hash 进 to_dict 仅 debug=true 时。
