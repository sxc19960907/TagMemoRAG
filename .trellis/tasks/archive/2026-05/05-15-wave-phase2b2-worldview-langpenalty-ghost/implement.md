# Implement — Phase 2b-2: worldview gating + language penalty + ghost tag injection

执行清单按依赖序排列。每一步都是可独立 commit 的小切片；遇到失败先回到上一个绿色点再继续。

## 前置检查（开始前）

- [ ] 已读 `prd.md` 的 D1-D8 决策与 R1-R13 / AC1-AC10
- [ ] 已读 `design.md` 的模块边界、数据契约、关键算法步骤、失败语义
- [ ] 已读 `research/source-worldview-langpenalty-ghost.md`（V6 4 段调制器源逐行）
- [ ] 当前分支干净，跑一次 `uv run pytest -q` 全绿（应 354 passed）
- [ ] 跑一次 `uv run python scripts/run_eval_ci.py` 全绿（应 8 suites pass）

## 执行清单（按依赖序）

### Step 1: 前置基线 ✓

如前置检查所列。如有 fail，先修绿再开始。

### Step 2: Config 字段加挡 + GhostTag 数据类（M1）

- [ ] 2.1 `src/tagmemorag/config.py` `WavePhase1Config` 加 5 个新字段：
  - `lang_penalty_enabled: bool = False`
  - `lang_penalty_unknown: float = Field(default=0.4, ge=0.0, le=1.0)`
  - `lang_penalty_cross_domain: float = Field(default=0.3, ge=0.0, le=1.0)`
  - `core_boost_min: float = Field(default=1.20, ge=1.0)`
  - `core_boost_max: float = Field(default=1.40, ge=1.0)`
  - 加 `model_validator` 检查 `core_boost_max >= core_boost_min`（可选）
- [ ] 2.2 `config.yaml` 同步加 5 个字段
- [ ] 2.3 `src/tagmemorag/wave_tag_spike.py` 新增 `GhostTag` frozen dataclass（design.md "数据契约"）；在模块开头 export
- [ ] 2.4 跑 `uv run pytest tests/unit/test_config_env.py -q`，全绿

**Validation**: 新字段默认 lang_penalty_enabled=False；R10 雏形
**Review gate**: 默认值不破 R10

### Step 3: lang_penalty + core_boost helpers（M2）

- [ ] 3.1 `wave_tag_spike.py` 内新增 4 个 module-private 函数：
  - `_resolve_core_tag_set(raw, *, kb_name, settings) -> _ResolvedCoreSet`
  - `_resolve_core_boost_factor(query_vec, settings, *, pyramid_features) -> float`
  - `_per_tag_core_boost(is_core, individual_relevance, dynamic_core) -> float`
  - `_compute_lang_penalty(tag_name, query_world, settings) -> tuple[float, str]`
- [ ] 3.2 在文件顶部加 4 个 regex 常量（`_TECH_TAG_PATTERN` / `_TECH_WORLD_PATTERN` / `_SOCIAL_WORLD_PATTERN` / `_CJK_PATTERN`），`import re`
- [ ] 3.3 implement 时确认 `tag_governance` 暴露的 resolver — 如果没有 `resolve_tag_for_kb`，写一个 thin wrapper：
  - `_resolve_canonical_via_governance(kb_name, raw_tag, settings) -> str`
  - 内部 lazy-load policy（首次调用）并缓存到 module-level dict（key=kb_name+settings.id）
  - 调 governance 现有 `resolve_tag` API；任何异常 ⇒ return raw_tag
- [ ] 3.4 不接 apply_tag_boost 主路径，先做单测

**Validation**: 4 个 helper 函数纯算法（无 IO 依赖）
**Review gate**: lang_penalty_enabled=False 时 `_compute_lang_penalty` 永远返 1.0

### Step 4: 写 helper 单测（M3）

- [ ] 4.1 新建 `tests/unit/test_apply_tag_boost_modulators.py`，按 design.md "测试策略" 写 ≥10 段：
  - dedup / synonym resolve / unknown passthrough（3 段）
  - lang_penalty 4 种触发矩阵（disabled / technical / unknown / cross_domain / social）（5 段）
  - chinese 永不触发（1 段）
  - core_boost_factor 公式极值（logicDepth=1/coverage=0 → 1.40；logicDepth=0/coverage=1 → 1.20）（1 段）
  - per_tag_core_boost individual_relevance（1 段）
  - 暂跳过 `_inject_core_completion` / `_inject_ghosts`（Step 5 之后再补）
- [ ] 4.2 跑 `uv run pytest tests/unit/test_apply_tag_boost_modulators.py -v`，全绿

**Validation**: AC3 + AC4 + 部分 AC6 雏形
**Review gate**: lang_penalty 4 种矩阵覆盖完整

### Step 5: core completion + ghost injection 注入器（M4）

- [ ] 5.1 `wave_tag_spike.py` 新增 `_inject_core_completion(...)` + `_inject_ghosts(...)` + `_load_kb_tag_vectors_by_names(...)` 3 个函数（design.md "Core completion" / "Ghost injection"）
- [ ] 5.2 `_inject_core_completion` 的 SQL 用现有 `_phase0_registry_path(cfg)` + `create_registry(...)` pattern，复用 `_load_kb_tag_vectors` 的连接惯例
- [ ] 5.3 `tests/unit/test_apply_tag_boost_modulators.py` 加：
  - `test_inject_core_completion_pulls_missing_from_db`（用 fixture 写 tag + 调注入器验证返回 added 数）
  - `test_inject_core_completion_skips_already_present`
  - `test_inject_ghosts_dim_mismatch_skipped`
  - `test_inject_ghosts_negative_id_does_not_collide`
  - `test_inject_ghosts_empty_returns_unchanged`
- [ ] 5.4 跑单测全绿

**Validation**: AC5 雏形 + 部分 AC2
**Review gate**: 注入器返回值的 `(row, weight, is_core)` triple schema 一致

### Step 6: TagBoostInfo 扩字段 + apply_tag_boost 入参扩 + pyramid 路径接通（M5）

- [ ] 6.1 `wave_tag_spike.TagBoostInfo` 加 7 个新字段（design.md "数据契约"）。`to_dict` 同步。
- [ ] 6.2 `apply_tag_boost` 签名加 `core_tags: Sequence[str] = ()` + `ghost_tags: Sequence[GhostTag] = ()`。函数入口处：
  - resolve core_tags ⇒ `_ResolvedCoreSet`
  - 把 `info.core_tags_input` / `info.core_tags_resolved` 记录到所有 early-return 分支（spike_disabled / matrix_missing / no_tag_vectors / no_seeds 等）
- [ ] 6.3 重构 `_resolve_dynamic_boost`：返回 `_DynamicBoostResult(dynamic, query_world)` 或 dict。query_world 只有在 strategy ∈ {epa, pyramid} 且 EPA basis 可用时非空，否则 ""。implement 时如果改 signature 太破，可以选 alternative：让 `apply_tag_boost` 自己再调一次 `EPAProjector.project()`（成本仅 K=8 矩阵乘法），caching 优化留给后续 Phase。
- [ ] 6.4 strategy="pyramid" 路径下 candidate 收集替换为 `(row, weight, is_core)` triple 形式，weight 公式应用 `_per_tag_core_boost` 与 `_compute_lang_penalty`，统计 `lang_applied_count`
- [ ] 6.5 strategy="pyramid" 路径下，merge 完 spike + emergent 后调 `_inject_core_completion` + `_inject_ghosts`，统计 info 字段
- [ ] 6.6 dedup 入口前把 triple 砍回 `(row, weight)` 喂给 `_semantic_dedup`（is_core 暂不影响 dedup 行为）
- [ ] 6.7 `info.matched_tag_names` 包含 ghost names（已自然融入）
- [ ] 6.8 跑现有 `tests/unit/test_apply_tag_boost.py` + `tests/unit/test_epa_logic_depth.py` + `tests/unit/test_residual_pyramid.py`，全绿（默认 strategy=constant 路径不破）

**Validation**: AC1（API 字段未到，先确认核心算法）+ AC2 雏形 + AC7 雏形
**Review gate**: strategy ∈ {constant, epa} 路径下 core_tags / ghost_tags **完全无影响**（手动跑一遍带 core_tags 但 strategy=constant 的测，验证 boost_factor_applied 与不传时一致）

### Step 7: API 扩 SearchRequest + GhostTagSpec + 透传链路（M6）

- [ ] 7.1 `src/tagmemorag/api.py` 加 `GhostTagSpec(BaseModel)`（name / vector / is_core）；`SearchRequest` 加 `core_tags / ghost_tags` 字段；OpenAPI 自动反映
- [ ] 7.2 `/search` 路由把 SearchRequest 字段转成 `list[GhostTag]`（API spec → 内部 dataclass）传给 `execute_search`
- [ ] 7.3 `src/tagmemorag/search_runtime.execute_search` 加 `core_tags / ghost_tags` 关键字参数；透传给 `apply_tag_boost`
- [ ] 7.4 `_compute_search_id` / `_compute_cache_key` 是否需要把 core_tags / ghost_tags 纳入 cache key？**纳入**（不同 core/ghost 对应不同结果），implement 时把字段 hash 进 cache key。
- [ ] 7.5 跑 `uv run pytest tests/unit/test_m2_api.py tests/unit/test_manual_library_api.py -q`（API 层未破）
- [ ] 7.6 加 `tests/unit/test_apply_tag_boost.py` 3 段：
  - `test_apply_tag_boost_core_tags_recorded_in_info`
  - `test_apply_tag_boost_ghost_tags_appear_in_matched_names`
  - `test_apply_tag_boost_constant_strategy_ignores_core_ghost`

**Validation**: AC1 + AC2 + AC6（synonym resolve via fixture）
**Review gate**: cache key 纳入 core/ghost；OpenAPI 自动文档反映

### Step 8: 观测指标补齐（M7）

- [ ] 8.1 `src/tagmemorag/observability/metrics.py` 加 3 个指标：
  - `tag_lang_penalty_applied: Counter(kb_name, query_world_kind)`
  - `tag_core_tags_resolved: Histogram(kb_name)`
  - `tag_ghosts_injected: Histogram(kb_name, kind)` (kind ∈ hard/soft/skipped_dim)
  - 加 record 方法：`record_tag_lang_penalty_applied / record_tag_core_tags_resolved / record_tag_ghosts_injected`
  - **检查 `query_world_kind` / `kind` 是否在 `ALLOWED_LABEL_NAMES` 集合**，不在的话加进去（看 metrics.py 顶部 ALLOWED 集）
- [ ] 8.2 在 `apply_tag_boost` 出口处接入：
  - `record_tag_core_tags_resolved(kb_name, count=len(resolved_core.canonical))`
  - 每个 ghost：`record_tag_ghosts_injected(kb_name, kind="hard"|"soft"|"skipped_dim")`
  - lang_penalty 在 `_compute_lang_penalty` 调用处统一调 `record_tag_lang_penalty_applied(kb_name, kind)` 仅当 penalty < 1.0
- [ ] 8.3 `tests/unit/test_observability_metrics.py` 加 1 段：
  - `test_phase2b2_modulator_metrics_register_custom_series`
- [ ] 8.4 跑 `uv run pytest tests/unit/test_observability_metrics.py -v`，全绿

**Validation**: AC9
**Review gate**: 默认 strategy=constant 时这 3 个指标也能 inc 0 / observe 0 / 不出错；query_world_kind label 通过 `assert_label_contract`

### Step 9: 文档（M8）

- [ ] 9.1 README "Wave Phase 1 — Switching to ResidualPyramid" 段加一段 "External modulators (Phase 2b-2)"：
  - 何时用 core_tags：用户已知 query 的关键 tag，强制聚光灯
  - 何时用 ghost_tags：caller 有 KB 外的同义词向量（如外部模型生成的扩展 tag）
  - lang_penalty_enabled 何时开：当 EPA basis 有非技术 label（如训练后中文 / Politics 等真实标签）
  - 简短示例 curl
- [ ] 9.2 `docs/wave-phase1-architecture.md` 加 "External modulators (Phase 2b-2)" 子章节：
  - 4 段调制器接到主流程的位置图
  - langPenalty 触发条件矩阵（PRD 已列）
  - dynamicCoreBoostFactor 公式
  - ghost id 负数约定 + dim 校验
- [ ] 9.3 docs 里加一句 "Phase 3 会引入真 residual + detectCrossDomainResonance"

**Validation**: AC10
**Review gate**: 文档示例可复制运行；触发条件矩阵清晰

### Step 10: 全量回归（M9）

- [ ] 10.1 跑 `uv run pytest -q` 全套，全绿（应 354 + 新增 ~14-16 = ~370）
- [ ] 10.2 跑 `uv run python scripts/run_eval_ci.py` 全绿（spike-on baseline 仍过；strategy=constant 字节稳定）
- [ ] 10.3 跑 `uv run pytest tests/e2e/test_search_baseline_invariance.py -v`（spike-off 字节一致）
- [ ] 10.4 跑 `uv run python scripts/diag_pyramid_dynamic_boost.py`（sanity check Phase 2b-1 通路仍 PASS；本任务不改算法）
- [ ] 10.5 PR 描述附 10 个 AC 勾选状态 + Step 7 API 示例

**Validation**: AC1-AC10 全勾
**Review gate**: 不引入回归

## 验收命令汇总

```bash
# Step 4 + 5 helper 单测
uv run pytest tests/unit/test_apply_tag_boost_modulators.py -v

# Step 6 + 7 e2e 单测
uv run pytest tests/unit/test_apply_tag_boost.py -v

# Step 8 观测单测
uv run pytest tests/unit/test_observability_metrics.py -v

# Step 10 全量
uv run pytest -q
uv run python scripts/run_eval_ci.py
uv run pytest tests/e2e/test_search_baseline_invariance.py -v
uv run python scripts/diag_pyramid_dynamic_boost.py
```

## Review Gates

每步末尾 review gate 不通过就不进入下一步：
1. **Step 2 后**：默认 lang_penalty_enabled=False；R10 不破
2. **Step 3 后**：4 个 helper 是纯函数（无 IO 副作用），可独立单测
3. **Step 5 后**：注入器在 `existing` 为空 / candidates 为空时也能正常工作（max_base=1.0 兜底）
4. **Step 6 后**：strategy ∈ {constant, epa} 路径下 core_tags / ghost_tags 完全无影响（手动验证 boost 字节稳定）
5. **Step 7 后**：cache key 纳入 core/ghost；不同 core_tags 对应不同 search id
6. **Step 8 后**：query_world_kind label 通过 `assert_label_contract`
7. **Step 10 后**：8 个 hashing eval suite 仍过；spike-off invariance 字节一致

## Rollback Points

按倒序 git revert：
1. Step 9 → 文档变更，无影响
2. Step 8 → 撤回观测指标（dashboard 缺数据）
3. Step 7 → 撤回 API 扩字段（caller 不能传 core/ghost；wave_tag_spike 仍接受 kwarg）
4. Step 6 → 撤回 apply_tag_boost 改造（回到 Phase 2b-1）
5. Step 5 → 撤回注入器（无引用，安全删）
6. Step 4 → 撤回 helper 单测（无引用）
7. Step 3 → 撤回 helper 函数（无引用）
8. Step 2 → 撤回 config 字段 + GhostTag dataclass（pydantic 默认值消失，但默认 strategy=constant ⇒ 无影响）

**完整回滚**（紧急）：
```bash
# 配置软回滚
yq -i '.wave_phase1.lang_penalty_enabled = false' config.yaml

# 代码回滚
git revert <step2-commit>..<step10-commit>
```

## 工作量估计

| Step | 估时 |
|---|---|
| Step 1 (前置) | 0.05 天 |
| Step 2 (config + GhostTag) | 0.15 天 |
| Step 3 (4 helper) | 0.3 天 |
| Step 4 (helper 单测 ≥10 段) | 0.3 天 |
| Step 5 (注入器 + 单测) | 0.3 天 |
| Step 6 (apply_tag_boost 主路径接通) | 0.5 天 |
| Step 7 (API + search_runtime + 3 段烟雾测) | 0.4 天 |
| Step 8 (观测指标 + 单测) | 0.2 天 |
| Step 9 (文档) | 0.15 天 |
| Step 10 (全量回归 + PR 描述) | 0.1 天 |
| **合计** | **~2.5 天** |

## AC 验收状态（PR 描述用，待勾选）

- [ ] AC1：API SearchRequest 接受 core_tags 与 ghost_tags；OpenAPI schema 反映；老 caller 不变
- [ ] AC2：strategy="pyramid" + core_tags + ghost_tags 端到端跑通，TagBoostInfo 字段正确
- [ ] AC3：langPenalty 4 种触发矩阵全部命中（数学锁底单测）
- [ ] AC4：dynamicCoreBoostFactor 公式极值（1.40 / 1.20）锁底
- [ ] AC5：ghost dim mismatch 不抛异常 + skip + metric kind="skipped_dim"
- [ ] AC6：core_tags 含 synonym 经 resolve 到 canonical
- [ ] AC7：默认 strategy=constant + 不传 core/ghost + lang_penalty_enabled=false ⇒ 8 eval suite + spike-off invariance + 现有单测全绿
- [ ] AC8：strategy="pyramid" + lang_penalty_enabled=true + hashing fixture ⇒ baseline 不漂超 -2%（fixture 上 langPenalty 实际不触发）
- [ ] AC9：3 个观测指标 spike-on 调用后实际写入 + 单测锁底
- [ ] AC10：README + docs/wave-phase1-architecture.md 文档落盘
