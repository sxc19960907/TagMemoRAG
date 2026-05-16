# brainstorm: Phase 4 浪潮 V8 geodesicRerank 接入

## Goal

把 VCPToolBox `TagMemoEngine.geodesicRerank` (V8) 接入到 TagMemoRAG search 主路径，
作为 wave 算法主线的最后一块拼图：复用 Phase 1 spike propagation 已经计算出的 tag
能量场 (`accumulated_energy`)，对 wave_search 输出的 chunk 候选做基于「测地线贴地距离」
的二次重排，使排序在保留 KNN 语义匹配主信号的前提下偏向 tag 能量积累更密的候选。

## Background / Known Context

### 源算法（VCPToolBox V8）

- 入口：`TagMemoEngine.geodesicRerank(candidates, options)`，VCPToolBox/TagMemoEngine.js:537-640。
- 流程：
  1. 批量查 `chunks.file_id` → `file_tags.tag_id[]` 映射；
  2. 对每个候选 chunk，把 tag_ids 的 `lastEnergyField[tid]` 累加得 `totalEnergy / hitCount`；
  3. `hitCount < minGeoSamples`（默认 4）⇒ 该 chunk geoScore=0；
  4. 全表 `maxGeo` 归一化到 [0, 1]；
  5. `finalScore = (1-α)·knnScore + α·normalizedGeo`，默认 α=0.3；
  6. 按 finalScore 降序输出，**只重排不截断**。
- 三层防御：L0 energyField 空 / L1 hits 不足 / L2 全表 maxGeo=0 ⇒ 退化为原顺序。
- 副作用：每个候选挂上 `original_knn_score`、`geo_score`、`normalized_geo`、`geo_hit_count` 用于诊断。

### TagMemoRAG 现状（接入点 + 差异）

- Search 主路径：`src/tagmemorag/search_runtime.py:32-125 execute_search`，顺序：
  `lexical/ANN preselect → apply_tag_boost (spike → energy field) → wave_search → return`。
- spike 能量场：`apply_tag_boost` 内 `propagate()` 返回 `SpikeResult.accumulated_energy: dict[int, float]`
  （`src/tagmemorag/wave_tag_spike.py:55-171`），目前消化进 `context` 后丢弃，未透出给 `execute_search`。
- chunk→tag 映射：**不需要中间 `file_tags` 表**。每个 graph 节点的 metadata 里直接含
  `tags: list[str]`（见 `metadata_from_node` + `_apply_metadata_boost`），名→id 走
  `tag_store.lookup_tag_id(name)`。这是与源端 V8 最大的实现差异。
- TagBoostInfo 不含能量场字段；新增字段 / 单独通道二选一。
- wave_search 已对 `eligible_node_ids` 做了 metadata_boost / lexical_boost / 排序截断 top_k，
  V8 接在 wave_search 之后是最自然的落点。

### 兼容性约束（Phase 2b-2 / 3 / 3.5 已确立的范式）

- **单 flag 默认 false + 缺值/退化路径与现状字节等价**（hashing eval 8 套 baseline + e2e baseline invariance）。
- producer 始终跑（这里指 spike）/ consumer 由独立 flag 守门。
- 缺值回退（hitCount 不足、能量场为空、metadata 没 tags）= 保持原 KNN 顺序，不引入静默偏移。
- 新增 metric 仅在 enabled=true 时记录，标签卡控避免高基数。

### 已知不在本任务范围

- Phase 3 `cross_domain_resonance_enabled` / Phase 3.5 `intrinsic_residuals_enabled` readiness（翻 flag）。
- siliconflow.json 实库 baseline 重训。
- VCP 时间桶 / 多模态 / 反馈学习等 post-v1 路线。

## Assumptions (待确认)

- A1：V8 复用 `apply_tag_boost` 已经跑过的 `accumulated_energy`，不在 V8 内重跑 spike（性能 + 一致性）。
- A2：V8 默认 α、minGeoSamples 沿用源端（α=0.3, minGeoSamples=4），但本仓 chunk 平均 tag 数可能 <4，需要重测。
- A3：V8 的输入候选 = wave_search 当前输出的 top_k 列表（不引入过采样池）；改为「过采样 2K → V8 重排 → 截 top_k」是更大的改动，留作 open question。

## Open Questions

（已收敛 Q1–Q5，等下一轮扩展扫描）

## Decisions

- **D1 V8 与 Phase 1 spike 的依赖关系 = 硬依赖 + silent noop**
  - V8 仅在 `wave_phase1.enabled && wave_phase1.spike_enabled && geodesic_rerank_enabled` 三者全 true 时生效。
  - spike 关闭（kill switch）⇒ V8 静默 noop（不报错），记 metric `geodesic_rerank_skipped_total{reason="spike_disabled"}`。
  - **Why**：与源端 V8 语义一致（V8 本就是 spike 下游消费者）；零额外算力；与 Phase 2/3/3.5 「producer 始终跑 + consumer flag 守门」范式同构；运维关 spike 救火时 V8 连带降级，不引入新故障面。
  - **How to apply**：`apply_tag_boost` 已经在 spike 关时早返回 `skipped_reason="spike_disabled"`，V8 只在 `boost_info.skipped_reason is None && energy_field is not None` 时执行；其他所有 skipped_reason 也算 noop（matrix_missing / no_seeds / degenerate_context / zero_alpha 等）。

- **D2 候选池规模 = 过采样 K' = top_k × geodesic_oversample_factor（默认 2.0），V8 重排后截 top_k**
  - `wave_search` 增加 `rerank_pool_size: int | None = None` 参数：None ⇒ 现状（直接截 top_k）；非 None ⇒ 排序后取前 `rerank_pool_size` 个候选返回，由调用方再做重排+截断。
  - `execute_search` 在 `geodesic_rerank_enabled=true` 时计算 `pool = top_k * oversample_factor`，传给 `wave_search`，然后调用 V8 重排，最后截 top_k。
  - flag-off 路径：`rerank_pool_size=None`，`wave_search` 行为字节等价（不进入 oversample 分支）。
  - 暴露独立 config `wave_phase1.geodesic_oversample_factor: float = 2.0`，下限 1.0（=不过采样）；上限通过 lint 提示（>5.0 警告，无硬限制以便诊断）。
  - **Why**：召回率有正向潜力（V8 的核心价值，否则只是排序微调）；与源端 V6 + V8 组合语义一致；K 通常 ≤ 20，K' = 40 的额外排序代价可忽略；`rerank_pool_size=None` 守住 baseline invariance。
  - **How to apply**：oversample 只在 V8 enable 时启用，flag-off 路径与现状字节相等；factor 配置不暴露到 `POST /search` 请求体（避免心智膨胀，调试用 config）。

- **D3 minGeoSamples 默认 = 2，暴露 config**
  - 暴露 `wave_phase1.geodesic_min_geo_samples: int = 2`。
  - **Why**：本仓 fixture 实证 manual 级 tag count median=3, min=3，75% manual <4。沿用源端默认 4 ⇒ 大部分候选 hitCount<4 ⇒ geoScore=0 ⇒ V8 整体退化为 noop，diag 拉不出有效信号。降到 2 让密度低的 chunk 也能参与；diag 可观察实际 hit 分布后再调。
  - **How to apply**：文档（README + docs/wave-phase1-architecture.md Phase 4 段）说明源端默认 4 但本仓默认 2 的差异，并给"密度高（≥6/chunk）调到 4"的建议；diag 脚本输出 hitCount 直方图便于验证。

- **D4 α 暴露层级 = config，不暴露 API**
  - 暴露 `wave_phase1.geodesic_alpha: float = 0.3`，加载时 clamp 到 `[0.0, 1.0]`；`POST /search` 请求体不接收 α。
  - **Why**：与 D2 `geodesic_oversample_factor`、D3 `geodesic_min_geo_samples` 暴露层级一致；调参一处可改；生产灰度只需翻 `geodesic_rerank_enabled`；diag 脚本扫 α=0.1/0.3/0.5 用 settings override 即可，不污染 API schema。
  - **How to apply**：α 通过 settings 注入到 V8 函数，函数本身保留 `alpha: float` 形参方便单测；如果未来出现 query-级 A/B 需求（多租户 / 灰度），再升级到「config 默认 + API 可覆盖」即可（向后兼容地新增字段）。

- **D5 能量场透传 = `TagBoostInfo` 新增 `accumulated_energy: Mapping[int, float] | None` 字段**
  - `apply_tag_boost` 在 spike 成功分支把 `spike_result.accumulated_energy` 写入 info；所有 skipped_reason 早返回路径填 `None`。
  - `execute_search` 通过 `boost_info.accumulated_energy` 拉到能量场，传给 V8。
  - 序列化层处理：debug payload 现有 `to_dict` 已对 `_cross_domain_bridges` 等私有字段做过排除，对 `accumulated_energy` 同样不输出（或仅输出 entry 数量 `geodesic_energy_field_size`），避免 debug 响应体膨胀。
  - **Why**：`TagBoostInfo` 本就是 spike 诊断容器（已持 `seed_tag_ids / emergent_count / cross_domain_resonance`），新增 energy_field 与现有字段同语义同生命周期；零调用栈签名改动；与"在已有数据通道扩字段而非新增侧通道"范式一致。
  - **How to apply**：字段类型用 `Mapping[int, float] | None`，避免误改原 dict；spike emergent 已有 cap（默认几百 entry），不会膨胀 info；测试时直接构造 `TagBoostInfo(accumulated_energy={...})` 注入 V8 函数。

- **D6 MVP 范围 = 核心闭环 + diag + eval gate + filter 边界 + swap observability + lexical 兼容回归**
  - In MVP：
    - (核心) `geodesic_rerank` 算法本体 + 接入 `execute_search` + 单 flag `geodesic_rerank_enabled` 守门（默认 false）。
    - (c) `scripts/diag_geodesic_rerank.py`：扫 α / minSamples，输出 hitCount 直方图、rank 翻动分布、召回率前后对比。
    - (d) eval enabled-on 列单独 PASS gate（在现有 hashing eval 套件 + e2e baseline invariance 之上）。
    - (e) Lexical 兼容显式回归测试（lexical-only / hybrid 路径下 V8 行为符合预期）。
    - (f) filter 严格导致 `wave_search` 返回候选 < pool 时，V8 在现有候选上重排（不上溯放宽 filter）。
    - (g) `geodesic_rerank_swap_total{kind}` metric 三分类（`rank_changed` / `new_entry` / `lost_entry`），仅 enabled=true 时记录。
  - Out of MVP（明确 follow-up）：
    - (a) 打分函数参数化（`mean / sum / log_norm / max_pool`）—— 写死均值，预留 `_score_aggregator` 内部函数命名以便后续替换。
    - (b) 跨 query 能量场缓存 —— V8 内部不持有 cache，依赖调用方的 `accumulated_energy` 入参。
    - 把 V8 默认翻开（readiness 任务，与 Phase 3 / 3.5 readiness 合并 / 串联，独立任务）。
  - **Why**：(c)(d)(e)(f)(g) 都属于"上线 V8 之前必须有眼睛 + 必须不漂 baseline + 必须覆盖现有混合检索路径"的最小可观测性集合，单独拆任务会让本任务实际不可验收；(a)(b) 属于扩展能力，写死默认值不影响算法正确性。
  - **How to apply**：(a) 在 design 留扩展点注释（`# Phase 4.1: replace _score_aggregator with strategy lookup`）；其余 6 项进 implement.md checklist。

- **D7 V8 skipped reason 细分 = 区分 `spike_disabled / matrix_missing / no_seeds / no_candidates / energy_field_empty / max_geo_zero / lexical_only_path` 等**
  - V8 入口前先按 boost_info 状态分类记 `geodesic_rerank_skipped_total{reason}`：
    - `spike_disabled`：`wave_phase1.spike_enabled=false` 早返回。
    - `matrix_missing` / `no_seeds` / `no_candidates` / `degenerate_context` / `zero_alpha` / `degenerate_fused`：`apply_tag_boost.skipped_reason` 直透。
    - `energy_field_empty`：spike 跑成功但 `accumulated_energy is None or len()==0`。
    - `lexical_only_path`：`execute_search` 走 lexical-only fallback（ANN/wave 退化，spike 没机会跑）。
    - `max_geo_zero`：V8 跑了，但全表 hitCount 不足或 metadata 无 tags 导致归一化前 maxGeo=0。
  - **Why**：运维看板能直接定位"V8 为什么没跑"（配置关 vs 数据问题 vs 路径退化），而不是看到一个笼统 skipped 计数推不出原因；与 `apply_tag_boost.skipped_reason` 已有的细分粒度对齐；新增标签 cost 极低（一处判断 + reason 字符串集合白名单）。
  - **How to apply**：reason 字符串纳入 allowed label set 白名单；diag 脚本扫每个 reason 的占比；文档表格列出每个 reason 的含义和应对建议。

## Requirements

### 算法本体（V8）

- 新模块 `src/tagmemorag/wave_geodesic_rerank.py` 暴露纯函数 `geodesic_rerank(candidates, *, energy_field, graph, kb_name, settings, alpha, min_geo_samples) -> list[Result]`。
- 每候选打分流程：
  1. 从 `graph.nodes[node_id]` 拿 `metadata.tags: list[str]`（用 `metadata_from_node` 一致接口）。
  2. 用 `tag_store.lookup_tag_id(name)` 把 tag 名解析为 tag_id（缺失即跳过该 tag）。
  3. 从 `energy_field` 累加该 chunk 的 `tag_id` 命中能量，记 `totalEnergy / hitCount`。
  4. `hitCount < min_geo_samples` ⇒ `geoScore = 0`。
  5. 全表 `maxGeo` 归一化到 [0, 1]；`maxGeo == 0` ⇒ 整体退化（返回原 candidates 顺序）。
  6. `final = (1 - α) * knn_score + α * normalized_geo`；按 final 降序输出。
- 三层防御与源端等价：L0 `energy_field` 空 / L1 hits 不足 / L2 全表 `maxGeo == 0` ⇒ 退化为原顺序，不抛错。
- 不修改输入 `candidates` 列表（返回新列表，候选元素允许加 `geo_score / normalized_geo / geo_hit_count / original_knn_score` 诊断字段）。

### 配置 / Flag

- `wave_phase1.geodesic_rerank_enabled: bool = False`（消费侧守门）。
- `wave_phase1.geodesic_alpha: float = 0.3`（加载时 clamp `[0.0, 1.0]`）。
- `wave_phase1.geodesic_oversample_factor: float = 2.0`（下限 1.0）。
- `wave_phase1.geodesic_min_geo_samples: int = 2`（下限 1）。
- 启动期 settings 校验：上述四项越界即 ConfigError；α / factor 走 clamp + warn。

### 能量场透传

- `TagBoostInfo` 新增 `accumulated_energy: Mapping[int, float] | None`。
- `apply_tag_boost` 在 spike 成功路径写入；所有 skipped_reason 早返回路径填 None。
- debug payload `to_dict` 排除 raw dict，仅输出 `geodesic_energy_field_size: int`。

### 集成

- `wave_search` 新增 `rerank_pool_size: int | None = None` 参数：None ⇒ 现状（直接截 `top_k`）；非 None ⇒ 排序后取前 `rerank_pool_size` 个返回，由调用方再做截断/重排。
- `execute_search`：当且仅当 `wave_phase1.enabled && spike_enabled && geodesic_rerank_enabled && boost_info.skipped_reason is None && boost_info.accumulated_energy is not None`：
  1. `pool = max(top_k, ceil(top_k * geodesic_oversample_factor))`；
  2. 用 `rerank_pool_size=pool` 调 `wave_search`；
  3. 调 `geodesic_rerank(...)` 得到重排后的候选列表；
  4. 截 `top_k` 返回。
  其他情况：完全走现状路径，`rerank_pool_size=None`，字节等价。
- filter 极严格 ⇒ `wave_search` 候选 < pool 时，V8 在实际候选上重排，不放宽 filter；`maxGeo == 0` 时按 D6(f) 退回原顺序。

### Observability

- 新增 metric `tagmemorag_geodesic_rerank_skipped_total{kb_name, reason}`，仅 enabled=true 时记录；reason ∈ {`spike_disabled`, `matrix_missing`, `no_seeds`, `no_candidates`, `energy_field_empty`, `max_geo_zero`, `lexical_only`...}（与 `apply_tag_boost.skipped_reason` 集合 + V8 内部退化原因合并）。
- 新增 metric `tagmemorag_geodesic_rerank_swap_total{kb_name, kind}`，kind ∈ {`rank_changed`, `new_entry`, `lost_entry`}，仅 enabled=true 时记录；按重排前后 top_k 集合差与位置变更累加。
- 新增 metric `tagmemorag_geodesic_rerank_applied_total{kb_name}`，每次成功调用 +1（用于"V8 真的跑了"锁底）。
- 新增 metric `tagmemorag_geodesic_rerank_hit_count_observed{kb_name}` (Histogram or Summary)，每次重排时按候选 hitCount 入 bucket，便于直方图诊断。
- 所有 label 值都需在 allowed label set 内，无高基数。

### Diag 脚本

- `scripts/diag_geodesic_rerank.py`：
  - 入参：`--kb`、`--queries-file`、`--alpha "0.0,0.1,0.3,0.5"`、`--min-samples "1,2,4"`、`--top-k`、`--oversample`。
  - 输出：每组参数下 V8 的「召回前后差异 / hitCount 直方图 / 平均 rank 翻动 / max_geo_zero 比例 / skipped_total 按 reason 拆分」表格。
  - PASS gate：在 enabled-on 默认参数下，`max_geo_zero` 比例 < 50%、`applied_total > 0`，否则视为本仓数据下 V8 无信号，CI 显式提示。

### Eval 接入

- 现有 8 套 hashing eval baseline + e2e baseline invariance：默认 off 路径字节稳定（与 Phase 2b-2 / 3 / 3.5 同等约束）。
- 新增 enabled-on 列：基于现有 eval 套件加一组「`geodesic_rerank_enabled=true` + α/min_samples 默认值」运行，单独 PASS gate（不强制 ≥ baseline 召回，但记录 delta，进入 CI 看板）。
- 失败时不阻断 baseline gate（避免一次算法调整全套 eval 红）。

### Lexical 兼容（D6.e）

- 增加测试 `tests/unit/test_geodesic_rerank.py::test_lexical_only_path_uses_metadata_tags`：`lexical_source_k>0` + ANN/向量路径退化时 V8 仍能在 lexical 召回的节点上拉到 `metadata.tags`，行为与纯向量路径一致（不会因 lexical 节点缺失某些字段而 crash）。
- 增加测试 `tests/unit/test_geodesic_rerank.py::test_hybrid_path_swap_metric_records`：lexical + ANN 混合候选下 swap_total 按预期分类记录。

## Acceptance Criteria

- [ ] `geodesic_rerank` 纯函数实现完成，三层退化全部覆盖单测（energy_field 空 / hitCount 不足 / maxGeo=0）。
- [ ] 默认 off 路径下：8 套 hashing eval baseline + e2e baseline invariance 字节稳定。
- [ ] enabled=true 路径下：`execute_search` 调用顺序为 `spike → wave_search(pool) → geodesic_rerank → 截 top_k`，单测 + 集成测试都覆盖。
- [ ] flag-off 路径下 `wave_search(rerank_pool_size=None)` 行为与现状字节相等。
- [ ] `TagBoostInfo.accumulated_energy` 在 spike 成功路径填充、skipped 路径为 None；debug payload 不输出 raw dict、只输出 size。
- [ ] 四项 metric (`skipped_total / swap_total / applied_total / hit_count_observed`) 在 enabled=true 时按预期记录，标签均在 allowed label set 内。
- [ ] `scripts/diag_geodesic_rerank.py` 可在本仓 fixture 上跑通，输出表格 + PASS gate。
- [ ] Lexical-only / hybrid 路径下 V8 行为符合 D6.e 两条测试预期。
- [ ] filter 极严格导致候选 < pool 时 V8 不抛错，能正常重排或退化（D6.f）。
- [ ] README + docs/wave-phase1-architecture.md 加 Phase 4 段（公式 + 默认 off + α/min_samples 参考表 + 与源端默认值差异说明）。
- [ ] `wave_phase1.spec.md` / `database-guidelines.md` 等 spec 文件按 Phase 4 字段同步。

## Out of Scope

- Phase 3 / Phase 3.5 readiness 翻 flag。
- siliconflow.json 实库 baseline 重训（生产 readiness）。
- V8 默认翻开（独立 readiness 任务，与 Phase 3 / 3.5 readiness 串联）。
- 打分函数参数化（mean → sum / log_norm / max_pool 切换） —— Phase 4.1 后续。
- 跨 query 能量场缓存 —— 任何 cache 都不在 V8 内部，由调用方负责。
- 增加新的 chunk→tag 持久化中间表（直接复用 `metadata.tags` + `tag_store.lookup_tag_id`）。
- 改 spike 算法本身、调整 spike 参数；本任务只在 spike 输出之上做下游消费。
- 任何前端 / API schema 不向后兼容的变更（响应体只允许新增字段）。

## Definition of Done

- 单测覆盖 V8 算法本体（α/min_samples/maxGeo=0/能量场空/缺 metadata 各退化路径）+ search_runtime 集成 + Lexical 兼容 + filter 边界。
- e2e baseline invariance + 8 套 hashing eval 默认 off 字节稳定；enabled-on 列 PASS gate 接入。
- 新增 metric 标签均在 allowed label set 内；diag 脚本可跑出有效表格。
- 文档：README + docs/wave-phase1-architecture.md 加 Phase 4 段；spec 文件同步。
- 配置 schema 变更通过 settings 校验测试覆盖。

## Research References

- VCPToolBox `TagMemoEngine.geodesicRerank` — TagMemoEngine.js:537-640（源算法权威实现）。
- 浪潮主线已交付：
  - `.trellis/tasks/archive/2026-05/05-15-wave-phase2b-residualpyramid/` — Pyramid GS 引擎。
  - `.trellis/tasks/archive/2026-05/05-15-wave-phase2b2-worldview-langpenalty-ghost/` — worldview / langPenalty / ghost。
  - `.trellis/tasks/archive/2026-05/05-16-wave-phase3-residuals-resonance/` — detectCrossDomainResonance。
  - `.trellis/tasks/archive/2026-05/05-16-wave-phase3-5-intrinsic-residuals/` — intrinsic_residuals + Pyramid prior。
- 接入点：
  - `src/tagmemorag/search_runtime.py:32 execute_search`
  - `src/tagmemorag/wave_tag_spike.py:55 propagate` / `:915 apply_tag_boost`
  - `src/tagmemorag/wave_searcher.py:13 wave_search`
  - `src/tagmemorag/manuals.py:173 metadata_from_node`
  - `src/tagmemorag/tag_store.py:109 lookup_tag_id`

## Definition of Done

- 单测覆盖 V8 算法本体（α/min_samples/maxGeo=0/能量场空/缺 metadata 各退化路径）+ search_runtime 集成。
- e2e baseline invariance + 8 套 hashing eval 默认 off 字节稳定。
- enabled=on 列单独 PASS gate（参考 Phase 3 `pyramid+resonance` 做法）。
- 新增 metric 标签在 allowed label set 内，无高基数。
- 文档：README + docs/wave-phase1-architecture.md 加 Phase 4 段落（公式 + 默认 off + α/min_samples 参考表）。
