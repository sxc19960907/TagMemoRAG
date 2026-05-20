# 浪潮回归 Phase 1：共现矩阵 + V6 spike propagation

## Goal

把 Phase 0 落盘的 `manual_tags(position)` 数据消费起来：构建有向加权共现矩阵 + 在 query 触发时沿 tag 共现图做 V6 spike propagation，作为 query-vector 的语义增强通道（**不是** chunk-side 加分）。把 Phase 0 之后蛰伏的 tag 体系第一次接入 search 路径，为 Phase 2-5 的 EPA 训练 / ResidualPyramid / geodesicRerank 留出干净的扩展点。

## Background / Known Context

### 项目本意
TagMemoRAG 立项目标是用 VCPToolBox 的浪潮算法（Wave v6/v7/v8）做产品说明书的语义检索。Phase 0 已经把数据底盘搭好（`tags` / `manual_tags(position)` / `tag_intrinsic_residuals` 三张表 + `epa_basis.npz`），但 search 路径还没读这些表。Phase 1 是首次让 search **真正消费 tag 数据**。

### 源算法形态（详见 `research/source-tag-boost-and-spike.md`）
源头 `TagMemoEngine.applyTagBoost` 重写 query 向量（不是给 chunk 加分）：
- 从查询出发选 seed tags（源用 ResidualPyramid，Phase 1 用 top-K cosine 替代）
- seed tags 沿 directed cooccurrence matrix 做 V6 spike propagation（带 momentum、firing threshold、wormhole gate）
- 把传播激活后的 tag 集合做 weighted-mean 得到 contextVec
- 最终 `query' = (1-α)·query + α·contextVec`，α = `min(1, effectiveTagBoost)`
- 这个新 query' 替代原 query 进入 vector search

### Phase 1 的边界
- 移植：directed cooccurrence matrix builder（含 legacy fallback）+ V6 spike propagation（含 V7 wormhole gate，residuals 默认 1.0）
- 暂缓：ResidualPyramid（用 top-K cosine 替代 seed 选择）、worldview gating、language penalty、ghost tag injection、core-tag completion API
- 跟着加：完整的 kill switch + 可观测 + 文档

## Assumptions

- 假设 1：Phase 0 数据干净。`manual_tags(kb_name, manual_id, tag_id, position)` 的 position 都是 1-indexed（不为 0），`tags.vector` 都已填充。Phase 1 实现 legacy fallback 但不预设它常态触发
- 假设 2：tag 量级在 10⁴ 以下。共现矩阵用 `dict[int, dict[int, float]]` 而非 scipy.sparse 完全够用
- 假设 3：rebuild 是用户触发、低频事件。共现矩阵的"5 分钟 debounce"源行为不需要照搬 — 每次 rebuild 末尾构一次就行

## Resolved Decisions

### D1（已锁定）：spike_enabled 默认关闭，PR 内只刷 hashing baseline

新加 `wave_phase1.spike_enabled`，**默认 false**。原因：
- AC 锁住 spike off ⇒ master 字节一致（保留快速回滚通道）
- AC 锁住 spike on ⇒ 跑通新 baseline（验证算法本身工作）
- 用户在 `config.yaml` 显式打开后才生效，给运维一个观察窗口

PR 内交付：跑 `scripts/build_eval_baseline.py --embedder hashing` 在 spike on 状态下重生成 `tests/fixtures/eval/baselines/hashing.json`，提交差异作为算法接入的可观测证据。SiliconFlow baseline 留给本地 sanity，**不在 PR 内更新**（部署侧 API 不在我这边）。

### D2（已锁定）：dynamic_boost_factor 默认走常数策略

新加 `wave_phase1.dynamic_boost_factor_strategy: "constant" | "epa"`，**默认 "constant"**，常数值 1.0。原因：
- Phase 0 EPA 是 cold-start identity 基底，`logicDepth ≈ 0`
- 完全照搬源公式会让 `effectiveTagBoost ≈ baseTagBoost * 0.3 = 0.009`，spike 几乎不可见
- 等 Phase 2b ResidualPyramid + 真 PCA 上线后切到 `"epa"` 模式自动 ramp-up
- 测试好写，行为可预测

### D3（已锁定）：spike on 时关闭现有 chunk-side tag_boost

`wave_phase1.spike_enabled=true` 时，`wave_searcher` 内部跳过现有 `search.tag_boost` 的 chunk-side 加分逻辑，避免与新 query-vector 增强双算。新增 `wave_phase1.legacy_chunk_tag_boost`（默认 false）作为兜底开关；如果 spike 上线后质量回退，可以打开它快速排查。

旧 `search.tag_boost` 数值不动（仍是 0.03），但语义改变：spike 路径消费它作 base_tag_boost，chunk 路径只在 `spike_enabled=false` 或 `legacy_chunk_tag_boost=true` 时使用。

### D4（已锁定）：共现矩阵 = 每 KB 一个 npz 文件，写在 `data/_global/tag_cooccurrence/`

理由（详见 `research/python-port-mapping.md`）：
- 与 Phase 0 EPA basis 的 `data/_global/` 全局资产模式一致（atomic write、跨 KB 共享目录）
- 一个 KB 一个文件 ⇒ atomic-write 粒度合理，cold-start 加载只读取需要的 KB
- 没有 `manual_tags` 行的 KB 不写文件 ⇒ search 时 loader 看到缺文件直接短路

格式：sparse triplet (`source_ids, target_ids, weights`) + meta（`schema_version, built_at, kb_name`）。

### D5（已锁定）：spike 算法常数全照搬源默认值

源 `MAX_SAFE_HOPS=4 / BASE_MOMENTUM=2.0 / FIRING_THRESHOLD=0.10 / BASE_DECAY=0.25 / WORMHOLE_DECAY=0.70 / TENSION_THRESHOLD=1.0 / MAX_EMERGENT_NODES=50 / MAX_NEIGHBORS_PER_NODE=20` 全部照抄，写进 `wave_phase1` config 段。fixture 太小不会触发 cap 类边界（hops、emergent_nodes、neighbors_per_node），用合成 fixture 补单测。

### D6（已锁定 · 2026-05-15）：CI 与 baseline 都锁 spike-on

`scripts/build_eval_baseline.py` 加 `--spike-on/--spike-off` 互斥选项（默认 spike-on，与新 baseline 含义对齐）。`scripts/run_eval_ci.py` 在临时 config 中写 `wave_phase1.spike_enabled: true`，让 CI 跑出来的指标和 baseline 同源。原因：
- 部署侧 `config.yaml` 默认 spike off ⇒ 软回滚通道继续保留（D1 不变）
- CI 守护新算法的输出质量，而不是被关闭的代码路径
- 维护一份 baseline 比 选项 C 的双 baseline 简单

副作用：CI 跑得比 Phase 0 慢（多了一次 cooccurrence 构建 + 每个 query 一次 spike walk）。fixture 规模 < 50ms/query，可接受。

## Open Questions

无（所有 Blocking/Preference 都已锁定）

## MVP Scope

### M1. Co-occurrence matrix builder + 持久化
- 新模块 `src/tagmemorag/tag_cooccurrence.py`
  - `build_cooccurrence_for_kb(kb_name, conn, *, phi_max, phi_min, legacy_phi, max_tags_per_manual)` → `CooccurrenceMatrix` (dict-of-dict + edge count)
  - `save_cooccurrence(path, matrix, kb_name)` / `load_cooccurrence(path) -> matrix | None` — atomic write 模式
  - 完整复刻源 step 1-3：phi-pair 主路径、legacy position=0 fallback、性能 guard (n<2 或 n>100 跳过)
- 路径：`data/_global/tag_cooccurrence/{kb_name}.npz`，schema_version=1
- 单测：phi 公式正确性、direction 不对称（早 position → 晚 position）、legacy fallback 双向、cap n>100 跳过、空矩阵不写文件、atomic write 容错

### M2. V6 spike propagation 算法
- 新模块 `src/tagmemorag/wave_tag_spike.py`
  - `propagate(seed_weights, matrix, *, residuals, **constants) -> dict[int, float]`（accumulatedEnergy）
  - 严格按源 [4.5] 段：MAX_SAFE_HOPS / BASE_MOMENTUM / FIRING_THRESHOLD / BASE_DECAY / WORMHOLE_DECAY / TENSION_THRESHOLD / MAX_EMERGENT_NODES / MAX_NEIGHBORS_PER_NODE
  - tension = `coocWeight * residual`, residuals 默认 1.0（从 `tag_intrinsic_residuals` 表读，缺值回退）
- 单测：3-node chain 解析期望、wormhole gate 触发、neighbor cap、emergent cap、empty seeds 不爆炸、empty matrix 不爆炸

### M3. apply_tag_boost 集成
- 在 `wave_tag_spike.py` 增加 `apply_tag_boost(query_vec, *, kb_name, settings, base_tag_boost) -> (boosted_vec, BoostInfo)`
  - Step 1：seed selection — top-K cosine over canonical tag vectors（替代 ResidualPyramid）
  - Step 2：调用 propagate() 得到 accumulatedEnergy，归并 seeds + emergent
  - Step 3：semantic dedup（cosine > 0.88，权重 20% 转移）
  - Step 4：weighted-mean contextVec + L2 normalize
  - Step 5：fused = (1-α)·query + α·contextVec, α=min(1, effectiveTagBoost)
  - dynamic_boost_factor 按 D2 默认走常数策略
- 失败/降级：matrix 缺失、seeds 空、totalWeight=0 各分支返回原 query
- 单测：每个分支 + 完整 happy path

### M4. search_runtime / wave_searcher 集成
- `search_runtime.execute_search` 在 ANN/lexical 之后、`wave_search` 之前调用 `apply_tag_boost`（仅当 `wave_phase1.spike_enabled` 且 matrix 存在）
- `wave_searcher.wave_search` 增加 `disable_legacy_tag_boost` 参数；spike 开启时 search_runtime 传 True，跳过现有 chunk-side `metadata_field_boost` 中 tags 维度的加分（D3）
- BoostInfo 通过 `SearchExecution` 透传到 debug payload（API debug=true 模式可见）

### M5. Rebuild 生命周期接通
- `tag_rebuild.sync_rebuild_tags` 末尾追加 `build_cooccurrence_for_kb(kb_name, conn)` + 写盘
- `RebuildTask` 加字段：`tag_cooccurrence_edges` / `tag_cooccurrence_error`
- `incremental_rebuild` / full `build_kb` 都要走（已经统一过 sync_rebuild_tags 入口）
- 失败处理：matrix 构建失败不 fail rebuild，把错误打到 `tag_cooccurrence_error` 字段，下次 rebuild 重试

### M6. 配置 + 可观测 + 文档
- `config.py` 新增 `WavePhase1Config`（所有 D1-D5 的 knobs + spike 算法 8 个常数 + seed_top_k / seed_min_similarity / dedup_threshold / dedup_weight_transfer）
- `config.yaml` 加 `wave_phase1` 段，**默认 spike_enabled=false**
- `observability/metrics.py` 加 3 个 Prometheus 指标：
  - `tagmemorag_tag_cooccurrence_edges{kb_name}` Gauge
  - `tagmemorag_tag_cooccurrence_rebuild_duration_seconds{kb_name, outcome}` Histogram
  - `tagmemorag_tag_spike_propagations_total{kb_name, outcome}` Counter
- `docs/wave-phase1-architecture.md`：算法概览、kill switch、回滚、调参建议
- README "Tag Data Model" 章节加一段：spike 默认关闭、如何打开、与 chunk-side tag_boost 的关系

### M7. 回归 + baseline 重训
- 跑 `scripts/build_eval_baseline.py --embedder hashing` 在 `spike_enabled=true` 状态下生成新 baseline
- 记录每个 suite 的 metric 变化幅度，写进 PR 描述
- 全套 pytest 绿
- `tests/e2e/test_search_baseline_invariance.py` 在 spike off 模式下跑通（保留 Phase 0 不变性的另一面证据）

## Out of Scope（明确不做）

- ResidualPyramid 完整移植（Phase 2b）
- worldview gating / language penalty / ghost tag injection（依赖 ResidualPyramid 或 caller-side feature，未排期）
- core-tag completion API（需要 API 层带 core_tags 参数，独立任务）
- V7 真 residual 训练（Phase 3，本任务保持 residual=1.0 默认）
- V8 geodesicRerank（Phase 4，需要 lastEnergyField 已经在 spike 内部缓存好了但暂不消费）
- 现有 6 个 boost 旋钮的清理（Phase 5）
- siliconflow.json baseline 重训（部署侧 sanity，不在本 PR 内）
- 共现矩阵的增量更新（debounce + 滑窗）— 源行为，但 TagMemoRAG rebuild 频次低，每次全量重建即可

## Requirements

1. **R1（数据）**：每 KB 一个 `data/_global/tag_cooccurrence/{kb_name}.npz`，atomic write，schema_version=1，empty matrix 不落盘
2. **R2（算法）**：phi 公式 + 双向源 step 3 fallback + 8 个 spike 常数全部按源默认值，可通过 config 覆盖
3. **R3（集成）**：`search_runtime.execute_search` 单点接入；`wave_searcher` 接收 `disable_legacy_tag_boost` 参数避免双算
4. **R4（默认状态）**：`wave_phase1.spike_enabled=false` 默认，需运维显式打开
5. **R5（回滚）**：spike off ⇒ search 输出与 master 字节一致；删 `data/_global/tag_cooccurrence/` 不破坏 search
6. **R6（可观测）**：3 个 Prometheus 指标 + RebuildTask 字段 + BoostInfo 透传 debug payload
7. **R7（baseline）**：PR 内重生成 hashing.json，每个 suite metric 变化幅度记录到 PR 描述
8. **R8（生命周期）**：每次 rebuild 结束都重建 cooccurrence；失败不 fail rebuild

## Acceptance Criteria

- [x] AC1：`pytest` 全套通过（含新 unit + 现有 e2e 不退化）
- [x] AC2：构造 4-tag fixture，按 phi 公式手算的边权重与 builder 输出位元一致（snapshot test）
- [x] AC3：3-node chain 合成 fixture，spike 一跳后 accumulatedEnergy 与解析期望相等（算法锁底）
- [x] AC4：`wave_phase1.spike_enabled=false` 时 `tests/e2e/test_search_baseline_invariance.py` 全过（master 字节一致）
- [x] AC5：`wave_phase1.spike_enabled=true` 时 8 个 eval suite 通过新 hashing baseline -2% 阈值；新 baseline 提交进 PR
- [x] AC6：rebuild 跑两次，第二次 cooccurrence npz 除 `built_at` 外字节一致（确定性）
- [x] AC7：删 `data/_global/tag_cooccurrence/` 后服务启动正常 + search 不报错（spike loader 见缺文件短路）
- [x] AC8：wormhole gate 在合成 fixture 上触发（构造 coocWeight ≥ 1.0 的边并验证 decay 走 0.70 而非 0.25）
- [x] AC9：`spike_enabled=true` + `legacy_chunk_tag_boost=false`（默认）下，wave_searcher 不再消费 chunk-side tag_boost；翻成 `legacy_chunk_tag_boost=true` 后行为回退（escape hatch 测试）
- [x] AC10：rebuild 失败注入测试（mock builder 抛异常）：rebuild 任务 status="done" 但 `tag_cooccurrence_error` 字段非空，下次 rebuild 自动重建

## Definition of Done

- 新模块 `tag_cooccurrence.py` / `wave_tag_spike.py` 完成 + 单测 ≥80% 覆盖
- `search_runtime` / `wave_searcher` / `tag_rebuild` / `state.RebuildTask` / `config.py` / `config.yaml` / `observability/metrics.py` 改动落盘
- `data/_global/tag_cooccurrence/{kb_name}.npz` 在 fixture KB 上能跑出非空内容
- `tests/fixtures/eval/baselines/hashing.json` 在 spike on 状态下重训完成、提交
- `docs/wave-phase1-architecture.md` 描述算法 + kill switch + 回滚
- README "Tag Data Model" 加 Phase 1 段
- 全套 pytest 绿，所有新 AC 勾选
- 不引入新 production 依赖（本任务用 numpy/scipy 标准库已有，sklearn 是 Phase 0 已加）

## Decision Log (ADR-lite)

- **D1**: spike 默认关闭，PR 内只刷 hashing baseline
- **D2**: dynamic_boost_factor 默认 constant=1.0，可切 EPA 模式
- **D3**: spike 开启时 chunk-side tag_boost 自动关闭，legacy_chunk_tag_boost 兜底
- **D4**: 共现矩阵每 KB 一 npz，存 `data/_global/tag_cooccurrence/`
- **D5**: 8 个 spike 常数全照搬源默认值
- **D6**: CI 与 baseline 都锁 spike-on（baseline builder 加 --spike-on/off 选项，run_eval_ci 临时 config spike on）

## Research References

- `research/source-cooccurrence-matrix.md` — V7 buildDirectedCooccurrenceMatrix 逐行解读
- `research/source-tag-boost-and-spike.md` — applyTagBoost + V6 spike propagation 完整流程
- `research/python-port-mapping.md` — 模块边界、数据结构选型、生命周期接入点
- `research/phase1-open-questions.md` — 9 个开放问题 + 边缘 case + 参数默认值汇总
