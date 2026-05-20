# Implement — Phase 2b-1: ResidualPyramid + 完整 dynamicBoostFactor 公式 + 观测补齐

执行清单按依赖序排列。每一步都是可独立 commit 的小切片；遇到失败先回到上一个绿色点再继续。

## 前置检查（开始前）

- [ ] 已读 `prd.md` 的 D1-D7 决策与 R1-R10 / AC1-AC8
- [ ] 已读 `design.md` 的模块边界、数据契约、关键算法步骤、失败语义
- [ ] 已读 `research/source-residual-pyramid.md`（394 行源 + 移植深度选项）
- [ ] 当前分支干净，跑一次 `uv run pytest -q` 全绿（应 338 passed）
- [ ] 跑一次 `uv run python scripts/run_eval_ci.py` 全绿（应 8 suites pass）

## 执行清单（按依赖序）

### Step 1: 前置基线 ✓

如前置检查所列。如有 fail，先修绿再开始。

### Step 2: ResidualPyramid 模块 + 单测（M1）

- [ ] 2.1 新建 `src/tagmemorag/residual_pyramid.py`：
  - `PyramidTag` / `PyramidLevel` / `HandshakeFeatures` / `PyramidFeatures` / `PyramidResult` 5 个 frozen dataclass（字段见 design.md "数据契约"）
  - `ResidualPyramid` 类：`__init__(tag_rows, *, max_levels, top_k, min_energy_ratio, use_handshake_features, dim)`；`analyze(query_vec) -> PyramidResult`
  - 内部辅助：`_topk_cosine` / `_gram_schmidt_project` / `_compute_handshakes` / `_analyze_handshakes` / `_extract_features` / `_empty_result`
  - 不读 DB 不读文件：纯算法，tag_rows 由 caller 传入
- [ ] 2.2 写 `tests/unit/test_residual_pyramid.py`，≥6 段：
  - `test_analyze_empty_query_returns_empty_result`（query 全零 / `||q||² < 1e-12`）
  - `test_analyze_two_level_decomposition_with_synthetic_orthogonal_tags`（构造 6 个正交 tag，期望 levels=2、coverage 接近 1）
  - `test_gram_schmidt_handles_linearly_dependent_tags`（输入两个相同的 tag，第二个 basis_coeff 应 = 0）
  - `test_analyze_early_stops_on_min_energy_ratio`（造一个 query 让 level-0 解释 95%，期望 break；min_energy_ratio=0.1）
  - `test_extract_features_formula`（数学推导锁底：coverage=0.6, coherence=0.5, noise=0.2 ⇒ tag_memo_activation = 0.6*0.5*0.8 = 0.24）
  - `test_handshake_disabled_returns_zero_coherence`（`use_handshake_features=False` ⇒ handshake=None ⇒ tag_memo_activation=0）
- [ ] 2.3 跑 `uv run pytest tests/unit/test_residual_pyramid.py -v`，全绿

**Validation**: AC1 雏形 — 模块独立可测试
**Review gate**: 类是纯算法（不依赖 DB / config / settings），可在 mock tag_rows 上跑

### Step 3: 接 wave_tag_spike + 完整 dynamicBoostFactor 公式（M2）

- [ ] 3.1 `src/tagmemorag/wave_tag_spike.py` 加 import：`from .residual_pyramid import ResidualPyramid, PyramidResult, PyramidFeatures`
- [ ] 3.2 改 `_resolve_dynamic_boost` 签名加 `pyramid_features: PyramidFeatures | None = None` 关键字参数；按 design.md 的新逻辑加 `strategy == "pyramid"` 分支
- [ ] 3.3 改 `apply_tag_boost`：
  - 在 `_select_seeds` 调用之前判断 `strategy == "pyramid"`，若是则实例化 `ResidualPyramid` 跑 `analyze`，把 `levels[*].tags` 收集为 `seeds_with_sim`，每个 candidate weight = `contribution * (0.7 ^ level)`
  - 任何异常 ⇒ `pyramid_result = None`，回退到原 `_select_seeds`
  - 在调 `_resolve_dynamic_boost` 时把 `pyramid_features` 传过去
- [ ] 3.4 跑 `uv run pytest tests/unit/test_apply_tag_boost.py -q`，现有 10 段不应破（默认 strategy=constant 路径）

**Validation**: AC5（默认 constant 不破）；AC2 / AC3 雏形（pyramid 路径接通）
**Review gate**: strategy="constant" 路径完全字节级稳定（不实例化 ResidualPyramid）

### Step 4: Config 字段加挡（M3）

- [ ] 4.1 `src/tagmemorag/config.py` `WavePhase1Config`：
  - `dynamic_boost_factor_strategy` Literal 扩为 `"constant" | "epa" | "pyramid"`
  - 加 7 个新字段（按 design.md "Config 新字段"）
- [ ] 4.2 `config.yaml` 同步加 7 个字段（默认值与 pydantic 一致），strategy 注释更新枚举值
- [ ] 4.3 跑 `uv run pytest tests/unit/test_config_env.py -q`，全绿

**Validation**: AC5（向后兼容）
**Review gate**: 默认 strategy 仍 `"constant"`；R5 锁住

### Step 5: 观测指标补齐（M4）

- [ ] 5.1 `src/tagmemorag/observability/metrics.py`：
  - 加 4 个指标（按 design.md "观测指标"）：`tag_dynamic_factor` / `tag_pyramid_levels` / `tag_pyramid_explained_energy` / `tag_pyramid_features`
  - 加 2 个 record 方法：`record_tag_dynamic_factor` / `record_tag_pyramid`
- [ ] 5.2 `wave_tag_spike.apply_tag_boost` 出口处接入：
  - 每次成功算出 `dynamic`（clamp 后）⇒ `record_tag_dynamic_factor(kb_name, strategy, dynamic)`
  - strategy="pyramid" 且 `pyramid_result is not None` ⇒ `record_tag_pyramid(kb_name, levels=len(pyramid_result.levels), explained=pyramid_result.total_explained_energy, features={...})`
- [ ] 5.3 `tests/unit/test_observability_metrics.py` 加用例：
  - 验证 `record_tag_dynamic_factor` 写入 Histogram
  - 验证 `record_tag_pyramid` 同时写 3 个 metric（levels Histogram + explained Histogram + features Gauge）
- [ ] 5.4 跑 `uv run pytest tests/unit/test_observability_metrics.py -q`，全绿

**Validation**: AC7
**Review gate**: 在 strategy="constant" 时是否记录 `tag_dynamic_factor`？设计：仍记录（dynamic=1.0），便于 dashboard 看 traffic 比例。pyramid 相关指标只在 strategy="pyramid" 路径记。

### Step 6: 诊断脚本 + D8 决策（M5）

- [ ] 6.1 写 `scripts/diag_pyramid_dynamic_boost.py`：
  - 临时 data_dir + cfg `epa_min_k=4`
  - 12-tag fixture build_kb 触发 real-pca
  - 51 个 eval question 文本 → encode → 跑三组 strategy={constant, epa, pyramid}
  - 对每组输出 alpha 序列 mean/std/range/range/mean
  - 同时打印 pyramid 通路下的 features.tag_memo_activation / coverage / coherence 序列统计
  - 判定 D2 阈值（std > 0.005, range/mean > 0.1）PASS/FAIL，return-code 0 if pyramid PASS else 1
- [ ] 6.2 跑 `uv run python scripts/diag_pyramid_dynamic_boost.py`，把输出粘进 PR 描述
- [ ] 6.3 **决策点（D8 候选）**：
  - 如果 PASS ⇒ `epa_logic_depth_scale` 保持 Phase 2a 的 2.0
  - 如果 FAIL ⇒ 二分 / 调 `epa_logic_depth_scale`（试 1.0 / 3.0 / 5.0）找到最小达标值，更新 `config.yaml`，写 D8 回 PRD

**Validation**: AC6 + AC2 + AC3
**Review gate**: 诊断输出可读；PASS/FAIL 判断逻辑清晰；D8 回写 PRD

### Step 7: 文档更新（M6）

- [ ] 7.1 README "Wave Phase 1" 段加段落 "Switching to ResidualPyramid dynamic boost"：
  - 何时切：KB tag 数 ≥ 16（EPA 真 PCA 触发 + pyramid 多级分解都有意义）
  - 切之前先跑 `scripts/diag_pyramid_dynamic_boost.py` 确认三组对照
  - 出问题就退 `dynamic_boost_factor_strategy: epa` 或 `constant`；或保留 pyramid 关 `pyramid_use_handshake_features: false`
- [ ] 7.2 `docs/wave-phase1-architecture.md` 加 "ResidualPyramid: multi-level Gram-Schmidt" 子章节：
  - analyze 流程示意图
  - features 公式
  - 三种 strategy 对比表（constant / epa / pyramid 的公式 + 何时用）
  - 性能预算（每 query < 5ms）
- [ ] 7.3 docs 里加一句 "Phase 2b-2 会接 worldview gating / language penalty / ghost tag injection"，与 Phase 2a 文档前后呼应

**Validation**: AC8
**Review gate**: 文档不暴露内部实现细节过度承诺；只描述切换条件

### Step 8: 全量回归（M7）

- [ ] 8.1 跑 `uv run pytest -q` 全套，全绿（应 338 + 新增 ~10 = ~348）
- [ ] 8.2 跑 `uv run python scripts/run_eval_ci.py` 全绿（spike-on baseline 仍过；strategy=constant 字节稳定）
- [ ] 8.3 跑 `uv run pytest tests/e2e/test_search_baseline_invariance.py -v`（spike-off 字节一致）
- [ ] 8.4 PR 描述附 8 个 AC 勾选状态 + Step 6 诊断脚本输出 + D8 决策（scale 是否调过默认值）

**Validation**: AC1-AC8 全勾
**Review gate**: 不引入回归

## 验收命令汇总

```bash
# Step 2 单测
uv run pytest tests/unit/test_residual_pyramid.py -v

# Step 5 观测单测
uv run pytest tests/unit/test_observability_metrics.py -v

# Step 6 诊断
uv run python scripts/diag_pyramid_dynamic_boost.py

# Step 8 全量
uv run pytest -q
uv run python scripts/run_eval_ci.py
uv run pytest tests/e2e/test_search_baseline_invariance.py -v
```

## Review Gates

每步末尾 review gate 不通过就不进入下一步：
1. **Step 2 后**：ResidualPyramid 类是纯算法（不读 DB/settings），可独立单测
2. **Step 3 后**：strategy="constant" 路径字节稳定（test_apply_tag_boost.py 现有 10 段全绿）
3. **Step 4 后**：默认 strategy 仍 "constant"，pydantic 默认值向后兼容
4. **Step 5 后**：strategy="constant" 时也记录 `tag_dynamic_factor`（dashboard 看 strategy 流量分布）；pyramid 指标仅 strategy="pyramid" 时记
5. **Step 6 后**：D8 决策（epa_logic_depth_scale 是否调）写回 PRD
6. **Step 7 后**：三种 strategy 对比表完整、切换条件清晰

## Rollback Points

按倒序 git revert：
1. Step 7 → 文档变更，无影响
2. Step 6 → 撤回诊断脚本（不影响主路径）
3. Step 5 → 撤回观测指标（dashboard 缺数据，但不影响搜索）
4. Step 4 → 撤回 config 字段（pydantic 默认值消失，但生产侧 strategy="constant" 默认 ⇒ 无影响）
5. Step 3 → 撤回 wave_tag_spike 改动（strategy="pyramid" 不可用，但 constant/epa 路径不变）
6. Step 2 → 撤回 ResidualPyramid 模块（Step 3 已撤回 ⇒ 无引用，可安全删）

**完整回滚**（紧急）：
```bash
# 配置软回滚
yq -i '.wave_phase1.dynamic_boost_factor_strategy = "constant"' config.yaml

# 代码回滚
git revert <step2-commit>..<step8-commit>
```

## 工作量估计

| Step | 估时 |
|---|---|
| Step 1 (前置) | 0.05 天 |
| Step 2 (residual_pyramid + 6 单测) | 0.6 天 |
| Step 3 (wave_tag_spike 接 pyramid + 公式) | 0.4 天 |
| Step 4 (config 字段) | 0.1 天 |
| Step 5 (观测指标 + 单测) | 0.3 天 |
| Step 6 (诊断脚本 + D8) | 0.3 天 |
| Step 7 (文档) | 0.15 天 |
| Step 8 (全量回归 + PR 描述) | 0.1 天 |
| **合计** | **~2 天** |

## AC 验收状态（PR 描述用，待勾选）

- [ ] AC1：`src/tagmemorag/residual_pyramid.py` 落盘，L2 深度实现，单测 ≥6 段全绿
- [ ] AC2：strategy="pyramid" 路径在 12-tag fixture 状态下 `pyramid.depth ≥ 1`，`features.tag_memo_activation` 非常数
- [ ] AC3：完整公式数学推导锁底单测：activation=1.0/coverage=1.0/logic_depth=1.0/entropy=0 ⇒ dynamic_factor = 1.5
- [ ] AC4：strategy="pyramid" 退化路径全部不抛异常，`info.skipped_reason` 写明降级原因
- [ ] AC5：默认 strategy="constant" — 8 eval suite baseline 仍过；spike-off invariance 字节一致；test_apply_tag_boost.py 现有 10 段全绿
- [ ] AC6：诊断脚本可重复，三组对照输出 + D2 阈值 PASS/FAIL，return-code 0/1
- [ ] AC7：4 个观测指标在 spike-on 调用后实际写入；test_observability_metrics.py 加用例锁底
- [ ] AC8：README + docs/wave-phase1-architecture.md 文档落盘，三种 strategy 对比表 + 切换条件清晰
