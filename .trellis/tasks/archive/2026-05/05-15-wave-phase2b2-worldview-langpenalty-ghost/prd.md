# 浪潮回归 Phase 2b-2：worldview gating + language penalty + ghost tag injection

## Goal

Phase 2b-1 把 ResidualPyramid + 完整 `dynamicBoostFactor` 公式接通后，本任务把源 V6 `applyTagBoost` 里 **三个外围调制器** 补齐，让 strategy="pyramid" 通路与源 V6 行为对齐：

- **worldview gating**：基于 EPA `dominantAxes[0].label` 判断 query 所在"世界"，配合下面的 langPenalty 决定是否压制跨世界 tag。
- **language penalty**：query 处于非技术世界但 candidate 是纯英数技术词时，weight × `basePenalty`（社会世界开方软化）。
- **ghost tag injection + core tag completion**：caller 显式传入的 `core_tags`（字符串）、`ghost_tags`（带向量），绕过 cooccurrence / pyramid 直接进 candidate 列表，强制聚光灯。

依赖 Phase 2b-1 的 ResidualPyramid `levels` 输出和完整公式形态。本任务**不动**算法核心，只在 candidate 收集与注入层加调制器。

## Background / Known Context

### Phase 2b-1 末态契合点（从代码确认）

- `wave_tag_spike.apply_tag_boost`（src/tagmemorag/wave_tag_spike.py:391-481）已串好 8 步骨架。Phase 2b-2 改动落在两处：
  - **(3) candidate 收集**（pyramid 路径）：weight 公式从 `contribution * layer_decay` 升级为 `contribution * layer_decay * langPenalty * coreBoost`。
  - **(5) merge candidates 之后、(6) dedup 之前**：插入 [4.6] core completion + [4.7] ghost injection。
- `dynamicCoreBoostFactor`（源 line 96-98）= `core_boost_min + coreMetric * (core_boost_max - core_boost_min)`，`coreMetric = 0.5*logicDepth + 0.5*(1 - coverage)`。Phase 2b-1 PRD D3 把这部分挂在 Out of Scope；本任务接通。
- `EPAProjector.project()` 的 `dominantAxes[0].label` 已实现（`epa_projector.py:48`），label 来自 `_labels_for_axes`（real-pca）或 `axis-{idx}`（cold-start）。
- `tag_governance` 已有 synonym 表（src/tagmemorag/tag_governance.py:62, 257-285），caller 传 synonym 当 core_tag 时可以 resolve 到 canonical。
- API `SearchRequest`（api.py:175-185）目前没有 `core_tags` / `ghost_tags` 字段；`SearchFilters` 是 metadata 过滤，不是注入。

### 源 4 段调制器映射（详见 research/source-worldview-langpenalty-ghost.md）

| 源段 | 关键代码位置 | 移植到 |
|---|---|---|
| dynamicCoreBoostFactor 计算 | TagMemoEngine.js:96-98 | `wave_tag_spike` 内新增 `_resolve_core_boost_factor()` |
| coreBoost + langPenalty | TagMemoEngine.js:140-180 | candidate 收集时 weight 公式扩展 |
| core tag completion | TagMemoEngine.js:312-342 | candidate merge 之后 + dedup 之前 |
| ghost tag injection | TagMemoEngine.js:344-372 | core completion 之后 |

### langPenalty 触发条件矩阵（hashing fixture / siliconflow 部署）

| query | tag candidate | queryWorld（EPA basis labels） | 是否触发 langPenalty |
|---|---|---|---|
| "F07 sensor wire loose" | "filter-cleaning" | 任何 axis-N 或纯英 tag name | ❌（tag 含 `-`，但 isTechnicalNoise 要求长度 > 3，filter-cleaning 满足；queryWorld 也是技术世界 ⇒ 不触发） |
| "冷藏室温度太高" | "kitchen" | "axis-0" 或某英文 tag name | ❌（queryWorld 仍命中技术世界正则） |
| 中文 query | 中文 tag | — | ❌（tag 含中文 ⇒ isTechnicalNoise=false） |
| 假设 queryWorld="Politics-Society" | "kitchen" | non-technical | ✅ langPenalty=0.4（penaltyUnknown 软化） |

⇒ TagMemoRAG **当前 fixture 几乎不会触发 langPenalty**（EPA basis labels 都是英文 tag name，命中 isTechnicalWorld 正则），但代码路径必须存在，等真实部署 fine-tune 后的 EPA basis 出现非技术 label 时才生效。本任务的 AC 主要锁"代码路径正确 + 默认 off + 显式开后行为符合源公式"。

## Resolved Decisions

### D1（已锁定 · 2026-05-16）：Phase 2b-2 默认全部 off，opt-in

- `wave_phase1.lang_penalty_enabled: bool = False` — langPenalty 总开关，默认 off。
- `core_tags` / `ghost_tags` 入参默认空 list ⇒ 不触发 core completion / ghost injection。
- 默认 strategy=constant 状态下，本任务所有改动等价无操作（R5 沿用 Phase 2b-1）。
- 拒绝默认 lang_penalty_enabled=true：8 个 hashing eval suite 已锁 baseline，开启可能微漂；先观察期。

### D2（已锁定 · 2026-05-16）：core_tags / ghost_tags 经 SearchRequest 扩 API 暴露

- `SearchRequest` 加可选字段 `core_tags: list[str] = []` 和 `ghost_tags: list[GhostTagSpec] = []`。
- `GhostTagSpec` = `{name: str, vector: list[float], is_core: bool = False}`（pydantic model；vector 长度由 server 在 apply_tag_boost 入口处校验 = `model.dim`）。
- 透传链路：API → `SearchRequest` → `execute_search`（kwarg `core_tags=`, `ghost_tags=`）→ `apply_tag_boost`（kwarg）→ `_select_pyramid_candidates`（candidate 修饰）+ `_inject_core_completion` + `_inject_ghosts`。
- 拒绝放在 `SearchFilters`：filters 是 metadata 过滤 / 缩集合的语义；core/ghost 是注入 / 加权，语义不一致。
- 拒绝 caller 传向量字符串 base64：调试性差；改 list[float] JSON 直接走 pydantic。

### D3（已锁定 · 2026-05-16）：core_tags 自动 resolve synonym → canonical

- API 入口处先过 `tag_governance.resolve_tag_for_kb` 把 synonym 映射到 canonical name；core_tags 字段保留原始字符串到 `info.core_tags_input`，`info.core_tags_resolved` 写解析后的 canonical 列表。
- 重复 / 空串自动 dedup + drop。
- 未知 tag（不在 canonical 也不在 synonym）⇒ **保留原字符串**走 core completion 路径（DB 查 `tags.name=?` 仍可能命中 = 用户拼写差异）；仍查不到 ⇒ 静默 skip（计入 metric `core_tag_missing` 但不抛异常）。
- 拒绝直接拒绝未知 tag：caller 经常拼写不规范，影响 UX。
- 拒绝完全照搬源（不接 synonym）：TagMemoRAG 已有 governance 表，不用浪费。

### D4（已锁定 · 2026-05-16）：langPenalty 公式照搬源默认值

- `lang_penalty_unknown: float = 0.4`（queryWorld='Unknown' 时）
- `lang_penalty_cross_domain: float = 0.3`（queryWorld 已识别但非技术世界）
- "技术世界"判定：`re.fullmatch(r"[A-Za-z0-9\-_.]+", queryWorld)`（与源完全一致）。
- "技术噪音 tag" 判定：`re.search(r"[一-龥]", tag_name) is None and re.fullmatch(r"[A-Za-z0-9\-_.\s]+", tag_name) and len(tag_name) > 3`。
- 社会世界软化：`re.search(r"Politics|Society|History|Economics|Culture", queryWorld, re.IGNORECASE)` ⇒ `langPenalty = sqrt(basePenalty)`。
- 拒绝改公式：源做了大量 fine-tune，TagMemoRAG 没有反例数据支撑改它。

### D5（已锁定 · 2026-05-16）：core boost 范围 + 公式照搬源默认值

- `core_boost_min: float = 1.20` / `core_boost_max: float = 1.40`（源 coreBoostRange 默认）。
- `coreMetric = 0.5 * logicDepth + 0.5 * (1 - coverage)`（features.coverage 由 pyramid 提供；strategy != pyramid 时 coverage=0 ⇒ coreMetric = 0.5*logicDepth + 0.5）。
- `dynamicCoreBoostFactor = core_boost_min + coreMetric * (core_boost_max - core_boost_min)`。
- `coreBoost = dynamicCoreBoostFactor * (0.95 + individualRelevance * 0.1)`，`individualRelevance = candidate.similarity (or 0.5 if missing)`。
- 拒绝抽 `entropy_penalty` 类硬编码到 config：心智膨胀，源默认稳定。

### D6（已锁定 · 2026-05-16）：ghost tag 用负数 id，与 DB tag 不冲突

- `ghost_id_counter` 从 -1 开始递减；`info.matched_tag_names` 包含 ghost name 但 `seed_tag_ids` 不含负数。
- ghost vector 维度校验：与 `query_vec.shape[0]` 不一致 ⇒ skip 该 ghost，计数 `info.ghost_skipped_dim_mismatch`。
- ghost 名重复 / 与 candidate 同名：源不去重（ghost 仍单独注入；后续 semantic dedup 阶段按 cosine > 0.88 自动合并）。Python 端**沿用此语义**，简化逻辑。
- ghost weight 基准 `maxBaseWeight = max(adjusted_weight / dynamicCoreBoostFactor for c in candidates)` ⇒ ghost 权重和真候选同量级。空 candidates 时 maxBaseWeight=1.0。
- 拒绝 ghost 自己生成 vector（caller embed）：调用方应自己 encode；server-side embed 涉及 embedder 路由 + cost 控制，超出本任务。

### D7（已锁定 · 2026-05-16）：worldview gating 范围 = 仅供 langPenalty 用

- 源里 `queryWorld` 仅用于 langPenalty 判定（line 155, 161）；没有独立的 "worldview gating" 算法（源代码注释 line 170-173 写 "暂用 layerDecay 代替复杂的实时投影"）。
- Phase 2b-2 **不**再额外加投影正交性 gating；只把 `queryWorld` 暴露给 langPenalty + 写入 `info.query_world` 用于诊断。
- 后续 Phase 3 / 4 如果发现 worldview 单独有用再独立做。
- 拒绝 "实时正交性 gating"：源里就没做，过度移植。

### D8（已锁定 · 2026-05-16）：观测指标补 3 个

- `tagmemorag_tag_lang_penalty_applied`（Counter, labels: `kb_name, query_world_kind`，kind ∈ {`unknown`, `technical`, `social`, `cross_domain_other`}）：每次 langPenalty 实际触发并 < 1.0 时 inc。
- `tagmemorag_tag_core_tags_resolved`（Histogram, labels: `kb_name`，buckets=(0,1,2,3,5,8,13)）：每次 apply_tag_boost 入口 resolve 后实际生效的 core_tag 数。
- `tagmemorag_tag_ghosts_injected`（Histogram, labels: `kb_name, kind`，kind ∈ {`hard`, `soft`, `skipped_dim`}）：每次 apply_tag_boost 注入或拒绝的 ghost 数。
- 拒绝增加 `core_completion_count`（dashboard 价值不大；core_tags_resolved 已经覆盖输入侧）。

## Requirements

1. **R1（API 扩字段）**：`SearchRequest` 加 `core_tags: list[str] = []` 与 `ghost_tags: list[GhostTagSpec] = []`；`GhostTagSpec` 字段 `name / vector / is_core`，pydantic 校验 vector 元素都是 float。
2. **R2（透传链路）**：`execute_search` / `apply_tag_boost` 加 `core_tags` / `ghost_tags` 关键字参数，默认空；`search_runtime` 把 SearchRequest 字段传下去。
3. **R3（synonym resolve）**：`apply_tag_boost` 入口处 resolve core_tags 经 `tag_governance.resolve_tag_for_kb` 到 canonical（kb_name 限定）；保留原始与解析后两份记录到 TagBoostInfo。
4. **R4（candidate 收集时调制）**：strategy="pyramid" 路径下，pyramid candidates 的 weight 公式从 `contribution * layer_decay` 升级为 `contribution * layer_decay * lang_penalty * core_boost`；strategy != pyramid 路径**不接 langPenalty / coreBoost**（保持 Phase 1/2a 行为不变）。
5. **R5（core tag completion）**：strategy="pyramid" 路径下，candidate merge 之后、dedup 之前，对 missing core_tags 走 SQL `SELECT id, name, vector FROM tags WHERE kb_name=? AND name IN (?,?,?)`，用 `maxBaseWeight * dynamicCoreBoostFactor` 注入。
6. **R6（ghost injection）**：strategy="pyramid" 路径下，core completion 之后注入 hard / soft ghost；负数 id；vector dim 校验；与 candidate 同 schema。
7. **R7（worldview / langPenalty 实装）**：按 D4 的两套正则与 D7 的 queryWorld 来源。`lang_penalty_enabled=False` 时全部 langPenalty=1.0（不影响 weight）。
8. **R8（dynamicCoreBoostFactor 公式）**：按 D5 实装，作为 `_resolve_dynamic_boost` 的副产品或独立 helper（推荐独立 helper `_resolve_core_boost_factor(query_vec, settings, pyramid_features)`，输入与 `_resolve_dynamic_boost` 同）。
9. **R9（config 字段）**：加 `lang_penalty_enabled / lang_penalty_unknown / lang_penalty_cross_domain / core_boost_min / core_boost_max` 5 个字段；config.yaml 同步。
10. **R10（向后兼容 / 默认 off）**：默认 strategy=constant + core_tags=[] + ghost_tags=[] + lang_penalty_enabled=false ⇒ test_apply_tag_boost.py 现有 10 段 + Phase 2b-1 strategy=pyramid 单测全绿；spike-off e2e baseline invariance 字节稳定；8 个 hashing eval suite 不漂。
11. **R11（观测指标）**：按 D8 补 3 个 metric + 对应 record 方法；`apply_tag_boost` 出口处接入；test_observability_metrics.py 加用例。
12. **R12（单测）**：新增 `tests/unit/test_apply_tag_boost_modulators.py`（≥10 段）覆盖：langPenalty 4 种触发矩阵 + coreBoost 公式 + dynamicCoreBoostFactor 公式 + core completion + ghost injection（hard/soft/dim mismatch）+ synonym resolve；现有 `tests/unit/test_apply_tag_boost.py` 加 strategy=pyramid + core_tags / ghost_tags 烟雾测试。
13. **R13（文档）**：README "Wave Phase 1 — Switching to ResidualPyramid" 段加一段说明 core_tags / ghost_tags 入参与 lang_penalty_enabled 用法；docs/wave-phase1-architecture.md 加 "External modulators (Phase 2b-2)" 子章节。

## Acceptance Criteria

- [ ] AC1：API SearchRequest 接受 `core_tags` 与 `ghost_tags`；新增字段在 OpenAPI schema 出现；老 caller（不传）行为不变。
- [ ] AC2：`apply_tag_boost(strategy="pyramid", core_tags=["filter-cleaning"], ghost_tags=[GhostTagSpec(name="airflow", vector=[...], is_core=True)])` 成功执行，返回的 TagBoostInfo 标记 `core_tags_resolved=("filter-cleaning",)`、`ghosts_injected=1`、`matched_tag_names` 包含 "airflow"。
- [ ] AC3：langPenalty 4 种触发矩阵全部命中（D4 的 4 行）：unknown / cross-domain / social-soften / 技术世界不触发，均有数学锁底单测。
- [ ] AC4：dynamicCoreBoostFactor 公式锁底：logicDepth=1.0 / coverage=0.0 ⇒ coreMetric = 1.0 ⇒ factor = 1.40；logicDepth=0 / coverage=1.0 ⇒ factor = 1.20。
- [ ] AC5：ghost vector dim mismatch 不抛异常，skip 该 ghost 并 `info.ghost_skipped_dim_mismatch += 1`，metric `tag_ghosts_injected{kind="skipped_dim"}` 自增。
- [ ] AC6：core_tags 含 synonym（先在 fixture 写一对 `cooling-mode → cooling`），resolve 后 `info.core_tags_resolved == ("cooling",)`。
- [ ] AC7：默认 strategy=constant + 不传 core_tags / ghost_tags + lang_penalty_enabled=false ⇒ 8 hashing eval suite baseline 仍过；spike-off e2e baseline invariance 字节稳定；test_apply_tag_boost.py 现有 10 段 + Phase 2b-1 单测全绿。
- [ ] AC8：strategy="pyramid" + lang_penalty_enabled=true + 任意 query ⇒ 在 fixture 上不漂 baseline 超过 -2% 阈值（hashing fixture 上 langPenalty 实际不触发，因为 EPA labels 都是技术词；这是预期，AC 写明）。
- [ ] AC9：3 个观测指标在 spike-on 调用后实际写入；test_observability_metrics.py 加用例锁底。
- [ ] AC10：README + docs/wave-phase1-architecture.md 文档落盘，core_tags / ghost_tags / lang_penalty 用法示例 + langPenalty 触发条件矩阵。

## Definition of Done

- 4 段调制器全部接通（dynamicCoreBoostFactor + langPenalty + core completion + ghost injection）
- 默认 strategy=constant 不变；spike-off baseline invariance 不变；hashing eval suite baseline 不漂
- 全套 pytest 绿（含新增 ~12 段单测）
- 3 个观测指标补齐 + 单测锁底
- API SearchRequest 文档化（OpenAPI 自动生成 + README 示例）
- README + docs/wave-phase1-architecture.md 文档段落落盘
- AC1-AC10 全勾

## Out of Scope（明确不做，由 Phase 3 / 4 接）

- 真 `EPA.detectCrossDomainResonance()` 移植（仍 stub=0）
- 实时正交性 worldview gating（D7 锁不做）
- V7 真 `tag_intrinsic_residuals` 训练（**Phase 3**）
- siliconflow.json baseline 重训（**生产 readiness 单独任务**）
- V8 geodesicRerank（**Phase 4**）
- spike-on baseline 重训（默认 strategy=constant 字节稳定，langPenalty 在 hashing fixture 不触发）
- ghost 向量 server-side encode（caller 自己 encode）

## Decision Log (ADR-lite)

- **D1**: Phase 2b-2 默认全部 off（lang_penalty_enabled=false / core_tags=[] / ghost_tags=[]）
- **D2**: core_tags / ghost_tags 经 SearchRequest 扩 API 暴露（不放 SearchFilters）
- **D3**: core_tags 自动 resolve synonym → canonical（接 tag_governance）
- **D4**: langPenalty 公式照搬源默认值（unknown=0.4 / cross_domain=0.3 / social sqrt 软化）
- **D5**: coreBoostRange 照搬源默认 [1.20, 1.40] + dynamicCoreBoostFactor 公式 + individualRelevance 微调
- **D6**: ghost 用负数 id + dim 校验 skip + 复用 dedup 路径
- **D7**: worldview gating 范围仅供 langPenalty 用（不做独立投影 gating）
- **D8**: 观测指标补 3 个（lang_penalty_applied + core_tags_resolved + ghosts_injected）

## Research References

- **本任务** [`research/source-worldview-langpenalty-ghost.md`](research/source-worldview-langpenalty-ghost.md) — V6 applyTagBoost 4 段源逐行解析 + TagMemoRAG 现状映射 + 移植细节
- Phase 2b-1 [`research/source-residual-pyramid.md`](../05-15-wave-phase2b-residualpyramid/research/source-residual-pyramid.md) — pyramid 接口契约（caller 调用点）
- Phase 1 [`research/source-tag-boost-and-spike.md`](../archive/2026-05/05-14-wave-phase1-cooccurrence-spike/research/source-tag-boost-and-spike.md) — 源整体 8 步流程图
- Phase 2b-1 [`prd.md`](../05-15-wave-phase2b-residualpyramid/prd.md) — D2-D8 锁的 strategy="pyramid" + features 接口约束
