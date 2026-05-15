# 浪潮回归 Phase 2b：ResidualPyramid + dynamicBoostFactor 完整公式 + 外围特性 + 观测补齐

## Goal

把 Phase 1/2a 留下的"算法骨架成型 + 单参数旋钮"升级为源 V6/V7 `applyTagBoost` 的**完整 query-vector 增强 pipeline**。
Phase 1 已经把 spike + cooccurrence + dedup + alpha-blend 接通，Phase 2a 把 `_resolve_dynamic_boost` 升级为 `max(epa_floor, logicDepth*scale)`。Phase 2b 要把 **seed selector**（top-K cosine → ResidualPyramid Gram-Schmidt 能量分解）、**dynamicBoostFactor 公式**（单参数旋钮 → 含 `tagMemoActivation/coverage/resonance/activationMultiplier` 的源公式）、**外围调制器**（worldview gating / language penalty / ghost tag injection）、**观测指标**（Phase 2a D6 故意跳过的）一起到位。

为了把 PR 大小、baseline 漂动定位、回滚粒度控制住，Phase 2b 拆成 2 个串行子任务：

- **Phase 2b-1（本任务的算法核心）**：ResidualPyramid 移植 + 完整 `dynamicBoostFactor` 公式 + 观测补齐。Out: Pyramid `levels` 产 `tagMemoActivation` / `coverage` / 各级 seed 候选，公式里的 4 个项全部接通；新增 `tag_dynamic_factor` Histogram 等观测；hashing eval suite + e2e baseline invariance 仍过。
- **Phase 2b-2（外围调制器）**：worldview gating + language penalty + ghost tag injection。依赖 2b-1 的 Pyramid `levels` 输出和 EPA real-PCA `dominantAxes[0].label`；caller 传 `core_tags` / `ghost_tags` 入参；接 `tag_governance` synonym 表。

> 本 PRD 聚焦 **Phase 2b-1**。Phase 2b-2 在本任务完成后单独开 task。

## Background / Known Context

### 已落盘的 Phase 1/2a 现状（从代码确认）

- `wave_tag_spike.apply_tag_boost`（src/tagmemorag/wave_tag_spike.py:356-481）已实现完整 8 步骨架：seed select → spike → merge → dedup → context vec → dynamic boost → alpha blend → renormalize。
- seed selector 当前是 `_select_seeds`（top-K cosine + `min_similarity` 阈值），对应源 `[2] ResidualPyramid` 的 **option (b) substitute**（见 Phase 1 research/source-tag-boost-and-spike.md L62-66）。
- `_resolve_dynamic_boost`（line 323-353）当前公式 `max(epa_floor, logicDepth * scale)`，对应源公式的"只保留 logicDepth × 标量"形态（Phase 2a D4）。源完整公式在 Phase 1 research/source-tag-boost-and-spike.md L70-82：
  ```
  dynamicBoostFactor = (logicDepth * (1 + log(1+resonance)) / (1 + entropy*0.5)) * activationMultiplier
  ```
- EPA real-PCA 通路在 12-tag fixture + `epa_min_k=4` 状态下能跑出有判别力的 `logicDepth`（Phase 2a 诊断脚本 `scripts/diag_epa_logic_depth.py` 实测：alpha 序列 std=0.00524 / range/mean=1.17 / PCA explained_variance sum=0.98）。
- observability/metrics.py 已经有 `tag_cooccurrence_edges` / `tag_cooccurrence_rebuild_duration` / `tag_spike_propagations`，**没有** `tag_dynamic_factor` Histogram 也没有 ResidualPyramid 相关指标。
- config 里 `wave_phase1` 还有两个 source 引用过、Phase 1/2a 没用上的字段：`core_boost_min` / `core_boost_max`（见 phase1-open-questions.md L173-174）— 但当前 config.py 没加，Phase 2b 时一起补齐。

### 源公式 vs 当前 Phase 2a 简化形态对照

| 源项 | 来源 | Phase 2a 现状 | Phase 2b-1 需要做 |
|---|---|---|---|
| `logicDepth` | `EPAProjector.project()` | ✅ 已用，乘 `epa_logic_depth_scale=2.0` | 保留，但作为完整公式的一项 |
| `entropy` | 同上 | ❌ 没用 | 引入分母 `(1 + entropy*0.5)` |
| `resonance` | `EPA.detectCrossDomainResonance()` | ❌ Phase 0 没移植 → stub=0 | **决策点**：保持 stub=0，or Phase 2b 顺手移植 |
| `activationMultiplier` | `actRange[0] + features.tagMemoActivation*(actRange[1]-actRange[0])` | ❌ 没 ResidualPyramid → 当 1.0 | 接 ResidualPyramid 产的 `tagMemoActivation` |
| `coverage` | `pyramid.features.coverage` | ❌ 同上 → 当 0.5 | 接 ResidualPyramid 产的 `coverage`（用于 coreMetric，2b-2 范围） |
| `langPenalty` | 字符表 + queryWorld 标签 | ❌ 没做 | Phase 2b-2 |
| `coreBoost` | caller `coreTags` | ❌ 没做 | Phase 2b-2 |
| `layerDecay = 0.7^level` | pyramid 各级 | ❌ 没做（单层 cosine） | 跟 ResidualPyramid 一起 |
| ghost tag injection | caller 同义词 | ❌ 没做 | Phase 2b-2，接 tag_governance synonym |

### ResidualPyramid 在源里干嘛（从 Phase 1 research 摘录）

`pyramid.analyze(query)` 返回 `{levels, totalExplainedEnergy, finalResidual, features}`：
- 多级 Gram-Schmidt 能量分解：每一级从 tag 索引拉 top-K，做正交投影，"解释" query 的一部分能量。
- 各级 tag 带 `{id, name, similarity, contribution, handshakeMagnitude}`。
- `features.tagMemoActivation`、`features.coverage` 是从 levels 派生的标量（用于 `dynamicBoostFactor` 和 `coreMetric`）。
- 输出在 `[4] 候选收集` 段被用：每级 tag 进 candidates，带 `layerDecay = 0.7^level`。

**关键点**：源里 ResidualPyramid 是 tag candidate 的 **唯一来源**（替代当前 Phase 1 的 cosine top-K）。换 seed selector 同时换 candidate 数量级和分布——hashing dim=64 fixture 上效果未知。

## Assumptions（待 brainstorm 验证）

- A1：ResidualPyramid 在 hashing dim=64 / 12 tags fixture 上能跑出 ≥2 levels 的非平凡分解（不退化到单层）。
- A2：完整公式接通后，alpha 序列在 hashing eval suite 上仍满足 baseline -2% 阈值（spike-on baseline 不漂或微漂可重训）。
- A3：`resonance` 在 Phase 2b-1 范围内**不移植**，继续 stub=0；移到 Phase 2b-2 或 Phase 3 时再决策。

## Open Questions

(已全部由 D2-D7 锁定)

## Resolved Decisions

### D1（已锁定 · 2026-05-15）：Phase 2b 拆 2 个串行子任务

- 2b-1 算法核心 + 观测补齐；2b-2 外围调制器。
- 拒绝选项 A（一次性 4 项）：PR 体量大、baseline 漂定位难、回滚粒度粗。
- 拒绝选项 C（永久跳过外围）：worldview/langPenalty/ghost 是源 V6 完整公式的组成部分，不能放弃；只是延后。

### D2（已锁定 · 2026-05-15）：ResidualPyramid Python 移植深度 = L2 中等

- 多级 Modified Gram-Schmidt 投影（数值稳定版）+ level-0 handshake 子模块 + 完整 `tagMemoActivation = coverage * coherence * (1 - noise)`。
- 估计 ~180 LOC（new module `src/tagmemorag/residual_pyramid.py`）。
- features 输出：`depth / coverage / novelty / coherence / tagMemoActivation / expansionSignal` 全部产出但 caller 只读 `tagMemoActivation` 和 `coverage`。
- 拒绝 L1（最小可用）：`tagMemoActivation = coverage` 退化掉源公式的相干性/噪音调制；后续若发现 coherence 在 hashing dim=64 上太噪，可以临时把 `pyramid_use_handshake_features` 调成 false 退到 L1 等价（fallback 旋钮，不删模块）。
- 拒绝 L3（完整 1:1）：所有 levels 的 handshake 在源里只进 debug log，caller 不读。多算无收益。

### D3（已锁定 · 2026-05-15）：dynamicBoostFactor 公式默认参数 = 源默认

- `activationMultiplier ∈ [0.5, 1.5]`（源 + TAGMEMO_TUNING_GUIDE 默认）。
- `dynamicBoostRange ∈ [0.3, 2.0]`（沿用 Phase 1 已有的 `dynamic_boost_min` / `dynamic_boost_max`，配置字段不变）。
- 公式分母里的 `entropy * 0.5` 系数在源里硬编码，本任务**保持硬编码**（不再加旋钮，避免 config 心智膨胀；如果实测需要再独立抽 D）。
- `coreBoostRange` 留 Phase 2b-2，本任务**不动** config（避免 dead config 字段）。
- `resonance` 在公式里 stub `0.0`（源调用 `EPA.detectCrossDomainResonance()`，Phase 0/1/2a 没移植；Phase 2b-1 不引入；公式里 `log(1+0) = 0` ⇒ 该乘项退化为 1.0，等价"忽略 resonance"）。

### D4（已锁定 · 2026-05-15）：Phase 2a 字段保留，作为 pyramid 通路的后置乘子/下限

- `wave_phase1.epa_logic_depth_scale`（默认 2.0，Phase 2a 校准过）保留：Phase 2b-1 的 strategy="pyramid" 路径在算完源公式后，再乘 `epa_logic_depth_scale`，最后 `max(epa_floor, ...)` 兜底。
- 拒绝清理 / 标 deprecated：保留这两个旋钮给运维一个 escape hatch（hashing dim=64 与生产 384 dim 行为差异较大时不用改代码就能调）。
- strategy="epa" 路径**不变**（Phase 2a 形态保留，作为只调 logicDepth 不接 pyramid 的中间档）。

### D5（已锁定 · 2026-05-15）：strategy 枚举值新增 "pyramid"，默认仍 "constant"

- `wave_phase1.dynamic_boost_factor_strategy` 从 `"constant" | "epa"` 扩到 `"constant" | "epa" | "pyramid"`。
- 默认值保持 `"constant"`：CI / 部署侧无感升级；R5 锁住 hashing eval suite 字节稳定。
- 拒绝默认切 "pyramid"：需要 spike-on baseline 重训证明不漂，扩大 Phase 2b-1 范围。
- 拒绝 "auto"：引入额外代码路径 + 心智复杂度，给边缘场景过度设计。

### D6（已锁定 · 2026-05-15）：spike-on baseline 不重训

- CI `run_eval_ci.py` 跑的 `spike_enabled=true` 在 Phase 2b-1 默认 strategy="constant" 路径下与 Phase 2a 字节级等价（无 pyramid 调用，无完整公式调用）。
- `pyramid` 通路用诊断脚本 `scripts/diag_pyramid_dynamic_boost.py` 守护，**不进 CI eval baseline**。理由同 Phase 2a D6 跳过 b 那条。
- 拒绝重训：扩大 PR 范围，把"算法接通"和"算法效果验证"绑在一起，回滚困难。

### D7（已锁定 · 2026-05-15）：MVP 观测范围 = 4 个 metrics

- `tagmemorag_tag_dynamic_factor`（Histogram, labels: `kb_name, strategy`）：apply_tag_boost 出口处的 `dynamic` 值（clamp 后）。每次 spike-on 调用都记。
- `tagmemorag_tag_pyramid_levels`（Histogram, labels: `kb_name`）：每次 pyramid.analyze 实际跑出来的 levels 数（0 表示 query 退化或被早停）。
- `tagmemorag_tag_pyramid_explained_energy`（Histogram, labels: `kb_name`）：`pyramid.totalExplainedEnergy` 浮点序列。
- `tagmemorag_tag_pyramid_features`（Gauge, labels: `kb_name, feature`，feature ∈ {`tag_memo_activation`, `coverage`, `coherence`}）：最近一次 pyramid.analyze 的关键 feature 值。Gauge per kb 用于运维 dashboard 实时观测，不做长尾。
- 跳过 `epa_basis_train_kind` Gauge：已经在 Phase 2a `retrain_report` 的日志里记了；额外 metric 信息冗余。
- Phase 2b-2（worldview/langPenalty/ghost）会再加 `tag_lang_penalty_applied` 等指标，本任务不动。

### D8（已锁定 · 2026-05-15）：pyramid 后置 scale 单独旋钮 = 4.0

- 诊断脚本 `scripts/diag_pyramid_dynamic_boost.py` 在 hashing dim=64 / 12-tag fixture / 51 个 eval question 上跑出：
  - 默认 `pyramid_post_scale=2.0`（复用 Phase 2a 的 scale）⇒ pyramid alpha std=0.00152，**FAIL** D2 阈值。
  - 按 0.5 step 二分 / 抽样 4.0 / 6.0 ⇒ pyramid 在 `≥ 3.8` 时 PASS。
  - 选 `4.0` 作为默认值（留 ~5% 余量 + 整数易记忆 + 与诊断脚本默认一致）。
- 引入新字段 `wave_phase1.pyramid_post_scale`（默认 4.0），**与 strategy="epa" 用的 `epa_logic_depth_scale=2.0` 解耦**。理由：
  - pyramid 路径 `tag_memo_activation` 平均 ~0.17 ⇒ activation_mult ~0.67；epa 路径直接乘 logicDepth；公式形态完全不同，共用一个 scale 会破 Phase 2a 校准。
  - 解耦后两条通路互不影响：strategy="epa" 仍用 2.0（Phase 2a D7 校准），strategy="pyramid" 用 4.0。
- pyramid 路径下的 floor 仍读 `epa_floor`（共用，默认 0.0）。
- 拒绝复用 `epa_logic_depth_scale`（破 Phase 2a 校准）。
- 拒绝硬编码 1.0（默认 FAIL，不可用）。
- 终态诊断脚本默认参数 PASS（std=0.0057 / range/mean=1.25 / pyramid 与 epa 同量级且有完整 features 调制）。

## Requirements

1. **R1（ResidualPyramid 模块）**：新增 `src/tagmemorag/residual_pyramid.py`，实现 L2 深度的 `ResidualPyramid` 类：`analyze(query_vec) -> PyramidResult`，包括多级 Modified Gram-Schmidt 投影、level-0 handshake、`_extract_features`。
2. **R2（数据契约）**：`PyramidLevel` / `PyramidFeatures` / `PyramidResult` 用 `@dataclass(frozen=True)`，字段命名 snake_case 但语义一一对应源（`logic_depth` 已用驼峰则保持 driver 行为不动）。`features.tag_memo_activation = coverage * coherence * (1 - noise_signal)`。
3. **R3（接通 wave_tag_spike）**：`_resolve_dynamic_boost` 加 `strategy="pyramid"` 路径，公式：
   ```
   activation_mult = act_min + tag_memo_activation * (act_max - act_min)
   dynamic_factor = (logic_depth * (1 + log(1+resonance)) / (1 + entropy*0.5)) * activation_mult
   # resonance stub = 0.0 → log(1+0) = 0 → 该项 = 1
   # 后置兜底：再乘 epa_logic_depth_scale，再 max(epa_floor, ...)
   ```
   `apply_tag_boost` 在 strategy="pyramid" 时把 `_select_seeds` 替换为 `ResidualPyramid.analyze().levels[*].tags` 的 candidates 列表，每个 candidate 带 `layer_decay = 0.7^level`。
4. **R4（fallback 链路）**：strategy="pyramid" 但 ResidualPyramid 任一异常 / pyramid empty / features 退化 ⇒ 降级到 strategy="epa" 或 "constant"（不抛异常，不破搜索）。具体降级语义：异常 ⇒ 当 strategy="constant" 处理（最强稳）；pyramid empty 但 EPA 可用 ⇒ 当 strategy="epa"。
5. **R5（向后兼容）**：默认 `strategy="constant"`；spike-off 模式（`spike_enabled=false`）的搜索字节级稳定（e2e baseline invariance 不变）；spike-on 模式 baseline -2% 阈值不漂（hashing eval suite 8 个全过）。
6. **R6（config 字段）**：新增 `wave_phase1.pyramid_max_levels=3` / `pyramid_top_k=10` / `pyramid_min_energy_ratio=0.1` / `pyramid_layer_decay_base=0.7` / `activation_multiplier_min=0.5` / `activation_multiplier_max=1.5` / `pyramid_use_handshake_features=true`（D2 fallback 旋钮）。`dynamic_boost_factor_strategy` Literal 扩到 `"constant" | "epa" | "pyramid"`。
7. **R7（观测指标）**：observability/metrics.py 新增 D7 的 4 个 metric + 对应 `record_*` / `set_*` 方法；apply_tag_boost / ResidualPyramid.analyze 出口处接入；test_observability_metrics.py 加用例。
8. **R8（诊断脚本）**：新增 `scripts/diag_pyramid_dynamic_boost.py`，对 12-tag fixture + epa_min_k=4 + 51 个 eval question 跑 strategy={constant, epa, pyramid} 三组对照，输出 alpha 序列 std / range/mean 与 D2 阈值 PASS/FAIL，return-code 0/1。
9. **R9（单测）**：`tests/unit/test_residual_pyramid.py`（≥6 段：原始能量退化 / 多级正常分解 / Gram-Schmidt 线性相关 / 早停（minEnergyRatio）/ features 公式 / level-0 handshake）+ `tests/unit/test_apply_tag_boost.py` 加 strategy="pyramid" 用例（≥3 段：完整公式接通 / pyramid empty fallback / 异常 fallback）。
10. **R10（文档）**：README "Wave Phase 1" 段加 pyramid 切换说明；docs/wave-phase1-architecture.md 加 "ResidualPyramid: multi-level Gram-Schmidt" 子章节 + 三种 strategy 对比表。

## Acceptance Criteria

- [ ] AC1：`src/tagmemorag/residual_pyramid.py` 落盘，L2 深度实现，单测 ≥6 段全绿。
- [ ] AC2：strategy="pyramid" 路径在 12-tag fixture + epa_min_k=4 状态下：`pyramid.depth ≥ 1`（多数 query 应 ≥ 2，不退化到 0），`features.tag_memo_activation` 在 [0, 1] 范围内非常数。
- [ ] AC3：完整 dynamicBoostFactor 公式接通 — 当 activation=1.0 / coverage=1.0 / logic_depth=1.0 / entropy=0 时，`dynamic_factor = 1.0 * 1 / 1 * 1.5 = 1.5`（数学推导锁底单测）。
- [ ] AC4：strategy="pyramid" + 任一退化路径（query 全零 / EPA basis 缺失 / pyramid analyze 抛异常）⇒ apply_tag_boost 不抛异常，alpha 落入 dynamic_boost_min 兜底，`info.skipped_reason` 写明降级原因。
- [ ] AC5：默认 strategy="constant" 状态下 — 8 个 hashing eval suite baseline -2% 阈值仍过；spike-off e2e baseline invariance 字节一致；test_apply_tag_boost.py 现有 10 段全绿。
- [ ] AC6：诊断脚本 `scripts/diag_pyramid_dynamic_boost.py` 可重复运行，输出 strategy={constant, epa, pyramid} 三组 alpha 序列对照 + D2 阈值 PASS/FAIL，return-code 0/1。
- [ ] AC7：观测指标 4 个 metric 在 spike-on 调用后实际写入；test_observability_metrics.py 加用例锁底。
- [ ] AC8：README + docs/wave-phase1-architecture.md 文档落盘，三种 strategy 对比表 + 切换条件清晰。

## Definition of Done

- ResidualPyramid 模块落盘 + 完整 dynamicBoostFactor 公式接通
- 默认 strategy="constant" 不变；spike-off baseline invariance 不变；hashing eval suite baseline 不漂
- 全套 pytest 绿（含新增 ~10 段单测）
- 4 个观测指标补齐 + 单测锁底
- 诊断脚本对照三种 strategy，return-code = 0
- README + docs/wave-phase1-architecture.md 文档段落落盘
- AC1-AC8 全勾

## Out of Scope（明确不做，由 Phase 2b-2 / Phase 3 接）

- worldview gating / language penalty / ghost tag injection（**Phase 2b-2**）
- core tag boost + caller `core_tags` 入参（**Phase 2b-2**）
- `EPA.detectCrossDomainResonance()` 移植（**Phase 2b-2 或 Phase 3**，本任务 stub=0）
- V7 真 `tag_intrinsic_residuals` 训练（**Phase 3**）
- siliconflow.json baseline 重训（**生产 readiness 单独任务**）
- V8 geodesicRerank（**Phase 4**）
- spike-on baseline 重训（D6 锁住 — 默认 strategy=constant 字节稳定）
- 改 `wave_phase0.epa_min_k` 生产默认值（保持 8）

## Decision Log (ADR-lite)

- **D1**: Phase 2b 拆 2 个串行子任务（本任务 = 2b-1）
- **D2**: ResidualPyramid 移植深度 = L2 中等（Modified GS + level-0 handshake + 完整 tagMemoActivation 公式，~180 LOC）
- **D3**: dynamicBoostFactor 公式默认参数 = 源默认（actMul=[0.5,1.5]，entropy*0.5 硬编码，resonance stub=0）
- **D4**: Phase 2a 的 `epa_logic_depth_scale` / `epa_floor` 保留，作为 pyramid 通路后置乘子/下限
- **D5**: strategy 枚举值新增 `"pyramid"`（默认仍 `"constant"`）
- **D6**: spike-on baseline 不重训（默认 constant 字节稳定，pyramid 通路用诊断脚本守护）
- **D7**: MVP 观测范围 = `tag_dynamic_factor` + `tag_pyramid_levels` + `tag_pyramid_explained_energy` + `tag_pyramid_features`
- **D8**: pyramid 后置 scale 单独旋钮 `pyramid_post_scale`，默认 `4.0`（与 `epa_logic_depth_scale=2.0` 解耦；诊断脚本实测达 D2 阈值的最小整数）

## Research References

- **本任务** [`research/source-residual-pyramid.md`](research/source-residual-pyramid.md) — `ResidualPyramid.js` 394 行完整解析 + caller 用法 + Python 移植 surface 选项
- Phase 1 [`research/source-tag-boost-and-spike.md`](../archive/2026-05/05-14-wave-phase1-cooccurrence-spike/research/source-tag-boost-and-spike.md) — 源 [2] ResidualPyramid + [3] dynamicBoostFactor 公式逐行注释（L52-82）
- Phase 1 [`research/python-port-mapping.md`](../archive/2026-05/05-14-wave-phase1-cooccurrence-spike/research/python-port-mapping.md) — Python 移植蓝图，ResidualPyramid 选 option (b) 的理由（L62-66）
- Phase 1 [`research/phase1-open-questions.md`](../archive/2026-05/05-14-wave-phase1-cooccurrence-spike/research/phase1-open-questions.md) — Q1 EPA `dynamicBoostFactor` 公式行为分析（L9-30）
- Phase 2a [`prd.md`](../archive/2026-05/05-15-wave-phase2a-epa-realpca/prd.md) — D4 fallback 形态决策与 D6 跳过观测的理由
