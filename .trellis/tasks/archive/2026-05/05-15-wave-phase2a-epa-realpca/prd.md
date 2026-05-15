# 浪潮回归 Phase 2a：EPA real-PCA 通路验证 + dynamic boost 接通

## Goal

让 EPA 训练分支在合理规模下真正产出有判别力的 `logicDepth`，让 Phase 1 锁定的 `wave_phase1.dynamic_boost_factor_strategy="epa"` 通道可用。当前 master 上"真 PCA 路径走不通"是个组合症状（fixture 太小 + cold-start 永远 entropy≈1 + 没有针对 EPA 状态的可观测/单测），Phase 2a 要先**确诊问题在哪条链路**，再决定是修触发条件、扩 fixture、改 logicDepth 公式，还是其他方案。

## Background / Known Context

### Phase 0/1 留下的现状（从代码确认）

- `epa_basis.train_real_pca(...)` 已实现（src/tagmemorag/epa_basis.py:110-162）。KMeans → 聚类中心 → 加权 PCA → 按能量阈值选 K。
- `retrain_if_needed` 触发门槛：`tag_count >= epa_min_k * 2`（默认 16）。少于 16 ⇒ `build_cold_start_basis(dim, min_K=8)` ⇒ `orthoBasis = np.eye(dim, dtype=np.float32)[:K]`。
- EPA basis 是**全局**（`data/_global/epa_basis.npz`），训练样本是所有 KB 的 canonical tag 向量并集。
- Phase 1 `_resolve_dynamic_boost` 在 strategy="epa" 时调 `EPAProjector.project(query).logicDepth`，公式 `1 - normalized_entropy`，其中 `normalized_entropy = -Σ p log2(p) / log2(K)`。
- fixture 实测：4 个 manual × 平均 3 tags = **10 unique tags 全局**，远低于 16 阈值 ⇒ master 跑出来永远 cold-start。
- Phase 1 baseline 重训显示 8 个 suite metric 与 Phase 0 字节一致，与上面这条事实一致。

### cold-start 模式下 logicDepth 的退化路径

`orthoBasis = I[:K]` ⇒ `centered = query - 0` ⇒ `projections = query[:K]` ⇒ 各分量平方后归一化得 probabilities。dim=64 / K=8 时如果 query 接近均匀分布在前 8 维上，`normalized_entropy ≈ 1` ⇒ `logicDepth ≈ 0` ⇒ 进 Phase 1 的 `dynamic_boost_min=0.3` 兜底。

**这意味着**：cold-start 下 logicDepth=0 是结构性退化，不是 bug。Phase 2a 的核心问题是：**真 PCA 状态下 logicDepth 是否有判别力？**

### 已经掉在地上的事

- Phase 1 PRD 的 D2 决策预留了 strategy 切换："等 Phase 2b ResidualPyramid + 真 PCA 上线后切到 epa 模式自动 ramp-up"。Phase 2a 是"真 PCA"那一半。
- ResidualPyramid 的 features（`tagMemoActivation`, `coverage`）是 Phase 2b 的活；本任务**不**做。
- Phase 1 已经写了 `_resolve_dynamic_boost(..., "epa")` 路径并在 EPA 加载失败时 fallback 到 1.0；没有验证过它在真 PCA 状态下产出什么数。

## Assumptions（待 brainstorm 验证）

- A1：fixture 扩到 ~20 unique tags 后真 PCA 会触发，但 `logicDepth` 在 hashing dim=64 上仍可能噪音盖过信号。
- A2：用户的真实部署有足够 tag（≥16）能跑真 PCA，这个本地 fixture 的事被掩盖了。
- A3：`logicDepth` 单独一个轴可能不足；源 V6/V7 的 `dynamicBoostFactor` 公式还有 `resonance`、`activationMultiplier` 两个项，去掉这两项后 logicDepth 可能本身就不够用。

## Open Questions

(待 brainstorm 一问一答)

## Resolved Decisions

### D1（已锁定 · 2026-05-15）：Phase 2a 范围 = 诊断 + 接通（选项 B）

- 先写诊断脚本/单测在当前 fixture 上量化 cold-start vs real-pca 的 logicDepth 行为。
- 根据诊断结果分支：
  - 如果 real-pca 下 logicDepth 在 fixture query 集上**有**判别力 ⇒ 扩 fixture 让 CI 触发真 PCA + 加单测锁 alpha 浮动。
  - 如果**没**判别力（hashing dim=64 噪音压制） ⇒ 加一层 fallback 公式让数值有意义（具体形态待诊断后定，避免 Phase 2b 的 `tagMemoActivation/coverage` 重叠）。
- 拒绝选项 C（不诊断直接改公式）：违反"最少改动"原则。
- 拒绝选项 A（仅诊断不接通）：Phase 1 strategy="epa" 通道至少要有"在某种规模下能用"的状态。

### D2（已锁定 · 2026-05-15）：判别力指标 = alpha 序列 std + range/mean（选项 B）

- 量的是 `apply_tag_boost` 输出的 `boost_factor_applied` 序列（clip+min 之后），而不是中间 `logicDepth`。
- 阈值（**诊断阶段起点，可调**）：
  - `std(alpha) > 0.005`
  - `(max(alpha) - min(alpha)) / mean(alpha) > 0.1`
- 输入 query 集 = `tests/fixtures/eval/*.jsonl` 所有 question 文本（用 hashing embedder 编码）。
- 同时记录 cold-start 模式下的 alpha 序列作对照（应该是常数）。
- 拒绝选项 A（量中间变量）：Phase 1 的 clip+min 路径会把中间变量浮动磨掉，需要量端到端。
- 拒绝选项 C（量排序变化）：Phase 2a 范围太重，且 fixture 规模下 spike 本身被噪音吃掉。

### D3（已锁定 · 2026-05-15）：触发 real-pca 走"测试 cfg 调低 min_k + 小幅扩 fixture"（选项 D）

- 测试侧：相关诊断脚本/单测里用 `Settings(wave_phase0={"epa_min_k": 4})`，触发门槛从 16 降到 8。
- fixture 侧：给 1 个现有 manual 的 metadata 补 2 个 tag（全局从 10 → 12 unique），保险触发 `tag_count(12) >= min_k(4) * 2 = 8`。
- 生产侧：`config.yaml` `wave_phase0.epa_min_k` **保持 8 不动**（用户真实 KB 应该 ≥16 tags，不需要宽松默认；PCA 在 4 聚类上的统计稳定性差）。
- 现有 8 个 eval suite 的 fixture **不动** ⇒ baseline 不漂。
- 拒绝选项 A：8 个 eval suite fixture 全核对工作量过大。
- 拒绝选项 B（改生产默认）：影响真实部署的 PCA 稳定性。
- 拒绝选项 C（mock real-pca basis）：不是真路径，CI 上无法复现真 PCA 行为。

### D4（已锁定 · 2026-05-15）：fallback 形态 = logicDepth 放大系数（选项 B）

- 如果诊断发现 real-pca 下 logicDepth 在 fixture 上不达 D2 阈值，加单参数 fallback：`dynamic = max(epa_floor, logicDepth * scale)`。
- 新加 `wave_phase1.epa_logic_depth_scale: float = 1.0`（默认等于 Phase 1 现状）。
- 新加 `wave_phase1.epa_floor: float = 0.0`（默认 0；落到 dynamic_boost_min 兜底处理就行；如果诊断显示 floor 有用再调）。
- **如果诊断显示原始 logicDepth 就达标，scale 默认 1.0 即等价当前实现，不引入新字段** — 决策保持向前兼容。
- 拒绝选项 A（top-axis 集中度）：改了 logicDepth 语义。
- 拒绝选项 C（双模式 top1+entropy）：和 Phase 2b ResidualPyramid 的 `coverage` 重叠，过度设计。
- 拒绝选项 D（推迟到诊断后）：D1-D3 已锁定路径，预定 fallback 形态避免 implement 阶段中断。

### D5（已锁定 · 2026-05-15）：部署侧 strategy 默认仍 "constant"（选项 A）

- Phase 2a 只**接通**通道，不切默认。`wave_phase1.dynamic_boost_factor_strategy` 在 `config.yaml` 默认保持 `"constant"`。
- 运维显式改成 `"epa"` 才生效，给观察窗口（与 Phase 1 D1 `spike_enabled=false` 同结构）。
- 拒绝选项 B（默认切 epa）：需要 spike-on baseline 重训证明不漂，扩大 Phase 2a 范围。
- 拒绝选项 C（新增 "auto" 枚举值）：引入新代码路径 + config 心智复杂度，为边缘场景过度设计。

### D6（已锁定 · 2026-05-15）：MVP 范围 = a + c + d（最小核心 + PCA 能量输出 + 退化路径单测）

- **a 核心**：D1-D5 的诊断 + 接通 + fallback + 不切默认（基线 MVP）。
- **c 诊断脚本输出 PCA explained_variance**：诊断脚本同时打印 `pca.explained_variance_ratio_`（前 K 维），帮运维判断 KB 规模是否足够支撑真 PCA。零成本延伸。
- **d strategy="epa" 退化路径单测**：构造一个所有 query 投影都退化（logicDepth=0）的合成 fixture，验证 `apply_tag_boost` 不爆炸，正确走 `epa_floor` / `dynamic_boost_min` 兜底。
- **跳过 b 观测指标**：Phase 2b 改 `dynamicBoostFactor` 公式时统一加观测，避免 Phase 2a 加了又被 Phase 2b 改。
- **跳过 e siliconflow 双跑**：Phase 1 D1 已锁"siliconflow baseline 不在本 PR 内"，Phase 2a 沿用。

### D7（已锁定 · 2026-05-15）：EPA scale = 2.0（诊断后调整）

- 诊断结果：`scale=1.0` 下 real-PCA alpha 序列 `std≈0.00130`，未达 D2 的 `std(alpha)>0.005`。
- `scale=2.0` 下 real-PCA alpha 序列 `std≈0.00524`，`range/mean≈1.17`，满足 D2。
- `config.yaml` 的 `wave_phase1.epa_logic_depth_scale` 调整为 `2.0`；部署默认 `dynamic_boost_factor_strategy` 仍为 `"constant"`，因此未显式切 EPA 的部署行为不变。
- `epa_floor` 保持 `0.0`，退化 query 继续交给 `dynamic_boost_min` 兜底。

## Requirements

1. **R1（诊断脚本）**：新增 `scripts/diag_epa_logic_depth.py`（或等价单测）。在 `epa_min_k=4` + 12 unique tags fixture 状态下：
   - 训练 real-pca basis 并写盘
   - 用 8 个 eval suite 的 question 文本作为 query 集
   - 跑 `EPAProjector.project(q).logicDepth` 序列 + `apply_tag_boost(...).boost_factor_applied` 序列
   - 同步打印 `pca.explained_variance_ratio_`（前 K 维），cold-start 模式下打印对照值
   - 输出三段 metric：`std(logicDepth)` / `std(alpha)` / `range(alpha)/mean(alpha)`
2. **R2（fixture 扩展）**：给现有 1 个 manual 的 metadata 补 2 个新 tag，全局 unique tags 从 10 → 12。8 个 eval suite 的 fixture **不动**。
3. **R3（fallback 实现）**：`wave_tag_spike._resolve_dynamic_boost` 加 `epa_logic_depth_scale` / `epa_floor` 两个 knob，公式 `dynamic = max(epa_floor, logicDepth * scale)`。两个 knob 默认值（1.0 / 0.0）等价 Phase 1 现状，向前兼容。
4. **R4（接通验证）**：在 `epa_min_k=4` + real-pca 状态下，`apply_tag_boost` 输出的 alpha 序列满足 D2 阈值；如果 scale=1.0 不达标，调整 scale 至达标（或 brainstorm 时再回头讨论 fallback 不够用的情况）。
5. **R5（向后兼容）**：现有 8 个 eval suite metric 不漂；Phase 0 e2e baseline invariance 测试在 spike-off 模式下不变。
6. **R6（部署默认）**：`config.yaml` `wave_phase1.dynamic_boost_factor_strategy` **保持 `"constant"` 默认**，新加的 `epa_logic_depth_scale=1.0` / `epa_floor=0.0` 仅在切到 `"epa"` 模式时生效。
7. **R7（退化路径稳健性）**：补单测覆盖"strategy=epa + EPA basis 加载成功 + 但 query 投影退化（logicDepth ≈ 0）"路径，确认走 epa_floor / dynamic_boost_min 不爆炸。
8. **R8（文档）**：README "Wave Phase 1" 段加一段说明何时切 `dynamic_boost_factor_strategy="epa"`；docs/wave-phase1-architecture.md 加一段 "EPA dynamic boost: cold-start vs real-pca" 子章节。

## Acceptance Criteria

- [ ] AC1：诊断脚本 `scripts/diag_epa_logic_depth.py` 可重复运行，输出 cold-start vs real-pca 两组 (logicDepth 序列, alpha 序列, PCA explained_variance) 数据，并对照 D2 阈值给 PASS/FAIL 判定。
- [ ] AC2：`epa_min_k=4` + 12 unique tags fixture 下，`epa_basis.npz` 的 `train_kind="real-pca"`，`pca.explained_variance_ratio_[:K].sum() > 0.5`（统计稳定性兜底）。
- [ ] AC3：strategy="epa" + real-pca + 默认 scale=1.0 / floor=0.0 状态下，alpha 序列满足 `std > 0.005` 且 `range/mean > 0.1`（D2 阈值）。如果默认参数不达标，本任务 implement 阶段调整 scale 至达标，决策回写到 PRD。
- [ ] AC4：strategy="epa" + EPA basis 加载成功但 query 全零 / 投影退化时，`apply_tag_boost` 不抛异常，alpha 落入 `dynamic_boost_min` 兜底。
- [ ] AC5：现有 8 个 hashing eval suite 通过 baseline -2% 阈值；Phase 0 e2e baseline invariance 测试在 spike-off 模式下不变。
- [ ] AC6：`config.yaml` 默认 strategy 仍为 `"constant"`；epa_logic_depth_scale / epa_floor 新字段默认值与 Phase 1 现状语义等价。
- [ ] AC7：README + docs/wave-phase1-architecture.md 文档落盘，描述 EPA dynamic boost 切换条件。

## Out of Scope（明确不做）

- ResidualPyramid 移植（Phase 2b）
- worldview gating / language penalty / ghost tag injection（Phase 2b 之后）
- V7 真 residual 训练（Phase 3）
- siliconflow.json baseline 重训
- 修改 `epa_basis.train_real_pca` 的 KMeans/PCA 算法本身（保持 Phase 0 行为）
- 改生产侧 `wave_phase0.epa_min_k` 默认值（保持 8）
- 改生产侧 `wave_phase1.dynamic_boost_factor_strategy` 默认值（保持 "constant"）
- 加观测指标 `tag_dynamic_factor` Histogram（D6 跳过 b，留 Phase 2b）
- 双 embedder 验证（D6 跳过 e）
- Spike-on baseline 重训（baseline 不应漂；R5 锁住）

## Definition of Done

- 诊断脚本/单测 + fixture 扩展 + fallback 公式 + 退化路径单测 全部落盘
- 8 个 hashing eval suite 仍过 baseline -2% 阈值
- 全套 pytest 绿
- README + docs/wave-phase1-architecture.md 文档段落落盘
- 7 个 AC 全勾

## Decision Log (ADR-lite)

- **D1**: Phase 2a 范围 = 诊断 + 接通（选项 B）
- **D2**: 判别力指标 = alpha 序列 std + range/mean（选项 B）
- **D3**: 触发 real-pca = 测试 cfg `epa_min_k=4` + 小幅扩 fixture 12 unique tags（选项 D）
- **D4**: fallback 形态 = `dynamic = max(epa_floor, logicDepth * scale)`（选项 B）
- **D5**: 部署侧 strategy 默认仍 "constant"（选项 A）
- **D6**: MVP = a + c + d（最小核心 + PCA 能量输出 + 退化路径单测）
- **D7**: 诊断后 EPA scale = 2.0，floor = 0.0

## Research References

- Phase 1 `research/source-tag-boost-and-spike.md` — `dynamicBoostFactor` 公式 line 70-82
- Phase 1 `research/phase1-open-questions.md` — Q1 cold-start logicDepth 退化分析
- Phase 0 `research/wave-phase0-design-notes.md` — EPA cold-start basis 由来与生产部署 tag 规模假设
