# 回归原则：移除非 VCP 的 calibration 常数

## Goal

按用户原则"只移植 VCPToolBox 的浪潮算法，不引入其他东西"，移除我们在
Phase 2a / 2b-1 期间为了让 hashing 64 维 fixture 上数字好看而引入的两个
非 VCP 源端 calibration 常数：

- `epa_logic_depth_scale` (default 1.0 in code, but documented 2.0 in fixture testing)
- `pyramid_post_scale` (default 4.0 — the egregious one)

把它们都默认回 `1.0`（VCP 原版无 scale 等价于 ×1），文档里删掉
"calibrated on hashing dim=64 fixture" 这类承认过拟合的注释。

## VCP 源端实证（2026-05-17 verify）

VCP `TagMemoEngine.js:88`:
```javascript
dynamicBoostFactor = (logicDepth * (1 + resonanceBoost) / (1 + entropyPenalty * 0.5)) * activationMultiplier
```

- `logicDepth` 直接乘，**没有任何 scale 系数**
- 整个公式后**没有 post-scale 乘数**
- `activationMultiplier` 是 `actRange[0] + features.tagMemoActivation * (actRange[1] - actRange[0])`，与 fixture-tuning 无关

我们的 Python 实现在 `_resolve_dynamic_boost_with_world` 等位置加了：
- `epa_logic_depth_scale: 2.0`（仅 strategy="epa" 路径用）
- `pyramid_post_scale: 4.0`（strategy="pyramid" 路径终末乘数）

这两个**不在 VCP 源里**，是过拟合 fixture 的修补。

## 决策

- **D1 两个常数默认值改回 `1.0`**：让公式与 VCP 源端等价（×1 = 不参与）。
- **D2 不删 config 字段**：保留 `Field` 让 ops 仍可显式 override（类似 wave_phase1 flag 的范式），仅默认值变。
- **D3 接受 hashing baseline 漂移**：fixture 的 alpha series std/range 不再 PASS 当年 D2 阈值是预期的——那阈值本身就是为了过拟合而调的。重 capture baseline。
- **D4 Phase 2a 的 D2 阈值也撤掉**：`scripts/diag_pyramid_dynamic_boost.py` 不再 PASS gate，纯 informational。
- **D5 验收**：pytest 全绿；hashing CI 8/8 strict 绿（baseline 重新 capture 后阈值随之 derive）；不在乎 alpha series 是否还"明显变化"——那是 fixture 太小造成的，不该靠常数 scale 解决。

## Requirements

- 改 `src/tagmemorag/config.py`：
  - `epa_logic_depth_scale: float = Field(default=1.0, ge=0.0)` (already 1.0, just remove "scale=2.0 in tests" intent)
  - `pyramid_post_scale: float = Field(default=1.0, ge=0.0)` (was 4.0)
- 改 `docs/wave-phase1-architecture.md`：删 "calibrated to 4.0 on hashing dim=64 / 12-tag fixture" 等承认过拟合的句子；写明"VCP 源端无此常数，default=1.0 等价 VCP 原版"。
- 改 `scripts/diag_pyramid_dynamic_boost.py`：D2 PASS gate 改为 informational only，alpha-series std 阈值不再卡 CI。
- 重 capture hashing.json + siliconflow.json baseline。
- 检查现有 tests 是否有 case 强行设置 pyramid_post_scale=4.0 → 同步改或删（这些 test 是为过拟合写的）。

## Acceptance Criteria

- [ ] `pyramid_post_scale` 默认 `1.0`；`epa_logic_depth_scale` 默认仍 `1.0` 不动（已经是 VCP 等价）
- [ ] Docs 更新；过拟合相关的 calibration 注释删除
- [ ] `scripts/diag_pyramid_dynamic_boost.py` 把 D2 阈值改 informational
- [ ] hashing.json + siliconflow.json 重 capture（接受 baseline 数字浮动）
- [ ] pytest 全绿
- [ ] `run_eval_ci.py` 默认 hashing 8/8 strict 绿（baseline 重新 derive 后自然过）
- [ ] commit message 含 "回归 VCP 原则：移除两个非 VCP calibration 常数"

## Out of Scope

- 真 PDF manual ingest 工具（独立任务）
- 移除 `--no-default-thresholds` 默认 / `--informational-suites` 默认机制（独立任务，等真数据上完再决定）
- 算法本身改动（Phase 1-4 算法保留不动，只改这两个常数的 default）
- 增删 wave_phase1 字段

## Definition of Done

- 默认配置加载产物字节稳定（modulo 两个 default 值变化）
- pytest / hashing CI / siliconflow CI 三项全绿
- 文档反映"只移植 VCP，无 calibration"原则
