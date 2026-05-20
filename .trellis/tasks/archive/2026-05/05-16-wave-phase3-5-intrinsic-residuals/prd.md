# Phase 3.5：真 tag_intrinsic_residuals 训练 + wormhole/Pyramid 先验接通

## Goal

把 Phase 0 起就闲置的 `tag_intrinsic_residuals` SQLite 表激活，写入每个 tag 在 cooc 邻居子空间外的真实残差能量。online 路径把表查回来喂入两个下游：

1. `wave_tag_spike.propagate` 的 `residuals` 参数（当前无 caller 全走默认 1.0），让 wormhole gate `tension = cooc_weight × residual` 真的发挥语义独立性的过滤作用，不再退化为「cooc_weight ≥ tension_threshold」。
2. `ResidualPyramid` 候选 tag 的先验权重（当前所有 tag 同权），让骨架选取偏向真正"独立"的 tag。

副作用：给 Phase 4 真共振灰度打地基（每 tag 本征独立性是 weighted bridge 的归一化因子）。

## Background / Known Context

- **schema 已落盘**：`tag_intrinsic_residuals(tag_id PK, residual_energy DEFAULT 1.0, neighbor_count, computed_at)`，定义在 `src/tagmemorag/manual_registry.py:337-345`，无 producer 无 consumer，仅 `tests/unit/test_tag_store.py` 单测往里写过测试数据。
- **online 消费点 1（wormhole gate）**：`src/tagmemorag/wave_tag_spike.py:57` 的 `propagate(residuals=None, ...)` ⇒ `residuals_map.get(tid, 1.0)`，全仓 grep 无 caller 传值（Phase 1 design.md L505 明确"等 Phase 3 接 ResidualPyramid 时再扩展"）。
- **online 消费点 2（Pyramid 先验）**：`src/tagmemorag/residual_pyramid.py:160` 的 `_topk_cosine` 候选打分目前只用 cosine 相似度，无外部权重接口。
- **训练算法（V7 源端推断）**：`.trellis/tasks/archive/2026-05/05-14-wave-phase0-tag-data-model/research/source-data-model.md:140-155` 给了推断公式：对每 tag T，把 T.vector 投影到其他邻居张成的子空间，`residual_energy = ‖residual‖² / ‖T.vector‖²`，`neighbor_count` 即基底 tag 数。源端 loader（`TagMemoEngine.js:738-755`）有 `clamp(0.5, 2.0)` 的硬保护。
- **cooc 输入**：`CooccurrenceMatrix.edges: dict[int, dict[int, float]]`（有向加权图）已在 rebuild 流水线写盘（`tag_rebuild._rebuild_cooccurrence`），给训练用作"邻居"来源天然合适。
- **rebuild 入口**：`sync_rebuild_tags`（`tag_rebuild.py:42`）目前一次性：dirty 嵌入 → cooc 重建 → 持久化。Phase 3.5 的训练步合理插点是 cooc 重建之后。
- **baseline 风险**：默认 enabled 翻开会让 spike 路径权重重排，hashing eval 的 8 个 baseline + e2e baseline invariance 大概率漂；Phase 3 已确立"新算法默认 false + 单独 flag" 的兼容范式（`cross_domain_resonance_enabled`）。

## Assumptions (待用户确认)

- 训练是离线一次性 / 增量批处理任务（不在每次 search 路径上跑）。
- 邻居取 cooc 图同 tag 的出/入边联合（待定具体规则）。
- `residual_energy` 训练值范围归一到 (0, 1]（源端 loader 有 [0.5, 2.0] clamp，但训练公式 `‖res‖² / ‖vec‖²` 自然落 [0, 1]，clamp 仅作防御）。

## Decisions

- **D1 训练触发点 = 混合（rebuild 钩子 fail-soft + 独立 CLI）**
  - rebuild 流：`sync_rebuild_tags` 在 `_rebuild_cooccurrence` 之后追加 `_rebuild_intrinsic_residuals(kb_name, cfg)`，与现有钩子同构（try/except 吞错，error_type 通过 `TagRebuildReport` 上报，不阻塞 rebuild）。
  - 手动入口：`python -m tagmemorag retrain-residuals --kb=<name>`（或现有 CLI 子命令体系），用于调试 / 单独重训。
  - 共享底层 `train_intrinsic_residuals_for_kb(kb_name, conn, cooc_matrix, cfg) -> TrainReport`，rebuild 钩子和 CLI 都调它。
  - Why：与现有 `_rebuild_cooccurrence` fail-soft 范式同构；online 查到的值自动跟随 cooc；调试不被流水线劫持。

- **D2 邻居取法 = Top-N cooc weight（出+入边并集，N 默认复用 `pyramid_top_k=10`）**
  - 对每 tag T：取 cooc 图上 T 的出边 + 入边并集邻居，按边权（双向边取 max）降序，取前 N 作为 GS 基底。
  - Why：与 ResidualPyramid `_topk_cosine` 的 K 同源同量纲，配置语义一致；GS 代价 O(N·dim) 可控；边权降序天然过滤弱邻居噪声；残差能量跨 tag 可比。
  - 暴露独立 config `intrinsic_residual_top_n`（默认 = `pyramid_top_k`），便于诊断脚本扫描。

- **D3 默认 enabled 策略 = 单 flag `intrinsic_residuals_enabled` 默认 false，producer 始终跑**
  - Producer（rebuild 钩子 + CLI）无条件写 `tag_intrinsic_residuals` 表（低成本副作用，留作诊断 / 灰度准备）。
  - 消费侧 flag = `wave_phase1.intrinsic_residuals_enabled`（默认 false）：false ⇒ wormhole gate 仍走 residual=1.0 fallback，Pyramid 候选打分仍单一 cosine；true ⇒ wormhole gate `tension = cooc_w × residual`，Pyramid 候选加 residual 先验。
  - 单 flag 同步控两个消费点，避免组合爆炸。
  - Why：与 `lang_penalty_enabled` / `cross_domain_resonance_enabled` 范式同构；保 8 套 hashing eval baseline + e2e baseline invariance 字节稳定；生产灰度只需翻 flag。
  - 验收：默认 off 路径 baseline 不漂；diag 脚本扩 `pyramid+residuals` 列单独 PASS gate（参考 phase3 `pyramid+resonance` 做法）。

- **D4 缺值回退 = 1.0 + 缺值率 Counter metric**
  - flag=true 时，wormhole gate / Pyramid 先验查不到 tag 的 residual 行 ⇒ fallback = 1.0（与源端 V7 `loadIntrinsicResiduals` 缺值兜底一致；与 flag=off 全表行为等价，不引入迁移期路径突变）。
  - 新增 `tagmemorag_tag_intrinsic_residual_missing_total{kb_name, consumer="wormhole"|"pyramid_prior"}`，每次 fallback 触发 +1（仅 enabled=true 时记录），把"训练缺失"做成可观察问题。
  - Why：故障容忍 + 与源端一致 > 用低 fallback 在迁移期偷偷收紧门；新 tag / 训练缺失通过指标暴露，不靠副作用。

- **D5 Pyramid 先验接入 = multiplicative gating（`score = cosine × residual_energy`）**
  - `ResidualPyramid` 构造函数加可选 `residuals: Mapping[int, float] | None`；`_topk_cosine` 候选打分内部对 score 乘 `residuals_map.get(tag_id, 1.0)`。
  - 缺值 1.0 ⇒ flag-off 路径与现状字节等价（自动满足 baseline invariance）。
  - 与 wormhole gate `tension = cooc_w × residual` 数学结构同构，单 flag 同步控两点的语义保持一致。
  - 新增 Counter `tagmemorag_tag_pyramid_residual_prior_applied_total{kb_name}`：仅 enabled=true 时，每次 `_topk_cosine` 调用 +1，锁底"先验跑了"。
  - Why：实现最小；语义统一；flag-off 字节稳定无需特殊路径。

## Open Questions

- 已收敛：Pyramid 先验接入采用 multiplicative gating（`score = cosine × residual_energy`）。

## Requirements

- 训练 worker `train_intrinsic_residuals_for_kb` 可被 `sync_rebuild_tags` 钩子和独立 CLI 共同调用。
- rebuild 钩子失败 fail-soft（不阻塞 rebuild），错误类型记入 `TagRebuildReport`。
- CLI 子命令：`retrain-residuals --kb=<name>` 单 KB 重训，返回退出码 + 行数报告。
- 邻居选取：每 tag 取 cooc 出+入边并集，按 max(out_w, in_w) 降序前 N 个。
- N 由 config `wave_phase1.intrinsic_residual_top_n` 控制，默认 = `pyramid_top_k`。
- Producer 始终跑（rebuild 钩子 + CLI 无条件写表），与 enabled flag 解耦。
- 消费侧由 `wave_phase1.intrinsic_residuals_enabled` 单一 flag（默认 false）守门，true 时同步激活 wormhole gate 与 Pyramid 先验。
- 默认 off 路径下：8 套 hashing eval baseline + e2e baseline invariance 字节不漂。
- diag 脚本（`diag_pyramid_dynamic_boost.py` 或新增 `diag_intrinsic_residuals.py`）加 enabled-on 列单独 PASS gate。
- 缺值回退：wormhole gate / Pyramid 先验查不到 tag 行 ⇒ residual = 1.0（源 V7 兼容）。
- 新增 Counter `tagmemorag_tag_intrinsic_residual_missing_total{kb_name, consumer}`，仅 enabled=true 时记录。

## Acceptance Criteria

- [ ] `train_intrinsic_residuals_for_kb` 根据 cooc 出+入边 Top-N 邻居训练并 upsert `tag_intrinsic_residuals`。
- [ ] `sync_rebuild_tags` 在 cooc 重建后 fail-soft 触发 residual 训练，并在 `TagRebuildReport` 暴露行数 / 错误类型。
- [ ] `python -m tagmemorag retrain-residuals --kb=<name>` 可单 KB 重训，stdout 报告行数，失败返回非 0。
- [ ] `wave_phase1.intrinsic_residuals_enabled` 默认 false；默认 off 时既有 spike / pyramid / baseline 行为不变。
- [ ] enabled=true 时 wormhole `propagate` 收到 registry residual map，缺值按 1.0 回退并记录 missing metric。
- [ ] enabled=true 且 strategy=pyramid 时 `ResidualPyramid` 候选排序乘 residual 先验，并记录 prior-applied metric。
- [ ] 新增 / 更新单测覆盖训练公式、Top-N 双向邻居、CLI、rebuild fail-soft、默认 off 不漂、enabled-on 消费和指标。

## Out of Scope

- Phase 4 V8 `geodesicRerank`。
- 真共振 flag 翻开（`cross_domain_resonance_enabled` 留给独立 readiness 任务）。
- siliconflow.json 实库 baseline 重训（生产 readiness 单独任务）。

## Research References

- `.trellis/tasks/archive/2026-05/05-14-wave-phase0-tag-data-model/research/source-data-model.md:127-160` — V7 residual schema + 训练公式推断。
- `.trellis/tasks/archive/2026-05/05-14-wave-phase1-cooccurrence-spike/research/source-tag-boost-and-spike.md:170-225` — V7 wormhole gate 源逻辑。
- `.trellis/tasks/archive/2026-05/05-15-wave-phase2b-residualpyramid/research/source-residual-pyramid.md` — Pyramid 内部 GS 算法（训练侧可直接复用 `_gram_schmidt_project`）。
- `src/tagmemorag/residual_pyramid.py:257` — `_gram_schmidt_project` 现成 helper。
