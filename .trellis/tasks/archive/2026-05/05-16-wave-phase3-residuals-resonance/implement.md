# Implement — Phase 3：detectCrossDomainResonance

执行清单按依赖序排列。每一步都是可独立 commit 的小切片；遇到失败先回到上一个绿色点再继续。

## 前置检查（开始前）

- [ ] 已读 `prd.md` 的 D1-D6 决策与 R1-R11 / AC1-AC11
- [ ] 已读 `design.md` 的模块边界、数据契约、关键算法步骤、失败语义
- [ ] 已读 `research/source-cross-domain-resonance.md`（V6 EPAModule.js:170-201 逐行）
- [ ] 当前分支干净，跑一次 `uv run pytest -q` 全绿（应 381 passed）
- [ ] 跑一次 `uv run python scripts/run_eval_ci.py` 全绿（应 8 suites pass）
- [ ] 跑一次 `uv run python scripts/diag_pyramid_dynamic_boost.py`（应 overall: PASS）

## 执行清单（按依赖序）

### Step 1：前置基线 ✓

如前置检查所列。如有 fail，先修绿再开始。

### Step 2：Config 字段 + TagBoostInfo 扩字段（M1）

- [ ] 2.1 `src/tagmemorag/config.py` 的 `WavePhase1Config` 加：
  - `cross_domain_resonance_enabled: bool = False`
  - 不需要 model_validator
- [ ] 2.2 `config.yaml` 同步加 `cross_domain_resonance_enabled: false`（紧跟 `core_boost_max` 后）
- [ ] 2.3 `src/tagmemorag/wave_tag_spike.py` `TagBoostInfo` 加 2 字段：
  - `cross_domain_resonance: float = 0.0`
  - `cross_domain_bridges_count: int = 0`
  - `to_dict` 同步
- [ ] 2.4 跑 `uv run pytest tests/unit/test_config_env.py tests/unit/test_apply_tag_boost.py -q`，全绿

**Validation**: 新字段默认值不破 R5
**Review gate**: 默认 `cross_domain_resonance_enabled=False`

### Step 3：detect_cross_domain_resonance helper + 单测（M2）

- [ ] 3.1 `src/tagmemorag/wave_tag_spike.py` 加 module-level 常量 + helper（design.md "新 helper" 章节）
- [ ] 3.2 新建 `tests/unit/test_cross_domain_resonance.py` 写 ≥7 段（design.md "测试策略"）
- [ ] 3.3 跑 `uv run pytest tests/unit/test_cross_domain_resonance.py -v`，全绿

**Validation**: AC1 + AC2 + AC3 + AC4 锁底
**Review gate**: 阈值 0.15 hardcode（不暴露 config）；balance 计算正确

### Step 4：`_DynamicBoostResult` 扩 + `_resolve_dynamic_boost_with_world` 接通（M3）

- [ ] 4.1 `_DynamicBoostResult` 加 `resonance: float = 0.0` + `bridges: tuple[dict, ...] = ()`
- [ ] 4.2 `_resolve_dynamic_boost_with_world` 在 pyramid 分支末尾按 D2 接通：`enabled=False` ⇒ resonance=0；`enabled=True` ⇒ 调 helper
- [ ] 4.3 把 resonance / bridges 装进 `_DynamicBoostResult`
- [ ] 4.4 跑 `uv run pytest tests/unit/test_epa_logic_depth.py -v`，全绿（默认 enabled=False ⇒ 行为不变）
- [ ] 4.5 加 1 段 `test_pyramid_dynamic_boost_with_resonance_enabled_extends_factor`：mock 一个 fake projector / 直接调 `_resolve_dynamic_boost_with_world` 验证 enabled=true 路径

**Validation**: AC5 + AC6 锁底
**Review gate**: enabled=False 路径数学等价 stub=0

### Step 5：apply_tag_boost 出口写 info + metric 上报（M4）

- [ ] 5.1 `apply_tag_boost` 在 info_extra 里加 `cross_domain_resonance` + `cross_domain_bridges_count`
- [ ] 5.2 `src/tagmemorag/observability/metrics.py` 加 2 个 Histogram 定义 + 2 个 record 方法（buckets 见 PRD D3）
- [ ] 5.3 `apply_tag_boost` 在 `metrics.record_tag_dynamic_factor` 旁边接入 `record_tag_resonance_value` + `record_tag_resonance_bridges_count`，仅当 `cfg.cross_domain_resonance_enabled` 为 true
- [ ] 5.4 `tests/unit/test_apply_tag_boost.py` 加 1 段 `test_apply_tag_boost_resonance_disabled_default`：默认 enabled=false ⇒ info 字段=0，fused 与 Phase 2b-1 行为完全一致
- [ ] 5.5 `tests/unit/test_observability_metrics.py` 加 1 段 `test_phase3_resonance_metrics_register_custom_series`
- [ ] 5.6 跑全部新测 + 现有 test_apply_tag_boost.py + test_observability_metrics.py，全绿

**Validation**: AC7 + AC9 雏形
**Review gate**: 默认 disabled 时 metric 不调（avoid 噪声）

### Step 6：search_runtime 暴露 bridges 到 debug payload（M5）

- [ ] 6.1 `SearchExecution` 加 `tag_boost_bridges: tuple[dict, ...] = ()` 字段
- [ ] 6.2 `execute_search` 把 boost_with_world.bridges 透传到 `SearchExecution`（apply_tag_boost 暴露 bridges 到 caller — 设计阶段 D5 选 info 只 count，bridges 单独传 — implement 时如果发现 apply_tag_boost 不暴露 bridges，**改为让 apply_tag_boost 返 `(vec, info, bridges)` 三元组**或加 `info._bridges` 字段供 search_runtime 读）

  **决策**：implement 阶段选最小改动。`apply_tag_boost` 已有 `(vec, info)` 二元组返回，加 `info` 内部不公开字段 `_cross_domain_bridges: tuple[dict, ...] = ()`（用 `field(default=(), repr=False)` 不入 to_dict），search_runtime 直接读 `boost_info._cross_domain_bridges`。
- [ ] 6.3 `search_runtime.search_debug_payload` 在 `payload["tag_boost"] = info.to_dict()` 后加：

  ```python
  if execution.tag_boost_bridges:
      payload["tag_boost_debug"] = {"cross_domain_bridges": list(execution.tag_boost_bridges)}
  ```
- [ ] 6.4 跑 `uv run pytest tests/unit/test_m2_api.py tests/unit/test_search_runtime*.py -q`（如存在），全绿

**Validation**: AC10
**Review gate**: bridges 仅当 enabled=true 且实际 trigger 时填；to_dict 面包不变

### Step 7：diag 重 calibrate（视实测）（M6）

- [ ] 7.1 修改 `scripts/diag_pyramid_dynamic_boost.py` 加 strategy=`pyramid+resonance`（即 enabled=true）的对照列输出
- [ ] 7.2 跑 `uv run python scripts/diag_pyramid_dynamic_boost.py`
- [ ] 7.3 检查 enabled=true 列的 D2 阈值（std > 0.005, range/mean > 0.1）是否 PASS
  - **若 PASS** ⇒ 不动 `pyramid_post_scale` 默认值 4.0；记录到 PR 描述
  - **若 fail** ⇒ sweep `pyramid_post_scale ∈ {1.0, 2.0, 3.0, 4.0, 5.0, 6.0}` 找最小 PASS；如果都 fail ⇒ 在 PR 描述里标记并降低 D2 严格度（这是 cold-start basis 的固有限制，本任务不解决）
- [ ] 7.4 如改默认值 ⇒ 同步 `config.py` + `config.yaml` + 注释

**Validation**: AC8
**Review gate**: enabled=true 列实测数据进 PR 描述

### Step 8：文档（M7）

- [ ] 8.1 README "External modulators (Phase 2b-2)" 段后加新段 "Cross-domain resonance (Phase 3)"：
  - 何时用：caller 想让"跨域"query 被 dynamicBoostFactor 真实放大
  - 何时不用：默认即可（cold-start basis 触发率低）
  - 简短示例 yaml + 手动开启步骤
  - log 域增益参考表（PRD 已列）
- [ ] 8.2 `docs/wave-phase1-architecture.md` 加 "Cross-domain resonance (Phase 3)" 子章节：
  - V6 公式接通位置（_resolve_dynamic_boost_with_world pyramid 分支）
  - bridges 数据契约
  - hardcoded 阈值 0.15 来源
  - 默认 off + diag 验证策略
- [ ] 8.3 docs 里加一句 "Phase 3.5 会引入真 tag_intrinsic_residuals + ResidualPyramid prior；Phase 4 V8 geodesicRerank"

**Validation**: AC11
**Review gate**: log 域增益表清晰；阈值 0.15 来源标注

### Step 9：全量回归（M8）

- [ ] 9.1 跑 `uv run pytest -q` 全套，全绿（381 + 新增 ~7-9 ≈ 388-390）
- [ ] 9.2 跑 `uv run python scripts/run_eval_ci.py` 全绿（8 hashing eval suite baseline 不漂）
- [ ] 9.3 跑 `uv run pytest tests/e2e/test_search_baseline_invariance.py -v`（spike-off 字节稳定）
- [ ] 9.4 跑 `uv run python scripts/diag_pyramid_dynamic_boost.py`（含 enabled=true 对照列）
- [ ] 9.5 PR 描述附 11 个 AC 勾选状态 + Step 7 calibrate 实测数据

**Validation**: AC1-AC11 全勾
**Review gate**: 不引入回归

## 验收命令汇总

```bash
# Step 3 helper 单测
uv run pytest tests/unit/test_cross_domain_resonance.py -v

# Step 4 公式接通单测
uv run pytest tests/unit/test_epa_logic_depth.py -v

# Step 5 + 6 e2e 单测
uv run pytest tests/unit/test_apply_tag_boost.py tests/unit/test_observability_metrics.py -v

# Step 7 calibrate
uv run python scripts/diag_pyramid_dynamic_boost.py

# Step 9 全量
uv run pytest -q
uv run python scripts/run_eval_ci.py
uv run pytest tests/e2e/test_search_baseline_invariance.py -v
```

## Review Gates

每步末尾 review gate 不通过就不进入下一步：

1. **Step 2 后**：`cross_domain_resonance_enabled` 默认 False；TagBoostInfo to_dict 含 2 个新字段
2. **Step 3 后**：helper 是纯函数；7 段单测全绿；阈值 0.15 hardcode
3. **Step 4 后**：enabled=False 路径数学等价 Phase 2b-1（test_epa_logic_depth.py 现有 5 段未漂）
4. **Step 5 后**：默认 disabled 时 metric 不 inc（避免噪声）；info.cross_domain_resonance=0
5. **Step 6 后**：bridges 仅当 enabled=true 且 trigger 时进 debug payload；to_dict 不含 bridges
6. **Step 7 后**：enabled=true 列实测数据落 PR；如重 calibrate ⇒ config 默认值更新
7. **Step 9 后**：8 hashing eval suite 仍过；spike-off invariance 字节一致

## Rollback Points

按倒序 git revert：

1. Step 8 → 文档变更，无影响
2. Step 7 → 撤回 diag 改动（dashboard 缺数据）
3. Step 6 → 撤回 bridges 暴露（debug payload 缺字段）
4. Step 5 → 撤回 metric + info 写入（observability 缺）
5. Step 4 → 撤回公式接通（resonance 仍 0；等价 Phase 2b-1）
6. Step 3 → 撤回 helper（无引用，安全删）
7. Step 2 → 撤回 config 字段 + TagBoostInfo 扩字段（pydantic 默认值消失，但默认 disabled ⇒ 无影响）

**完整回滚**（紧急）：

```bash
# 配置软回滚
yq -i '.wave_phase1.cross_domain_resonance_enabled = false' config.yaml

# 代码回滚
git revert <step2-commit>..<step9-commit>
```

## 工作量估计

| Step | 估时 |
|---|---|
| Step 1 (前置) | 0.05 天 |
| Step 2 (config + TagBoostInfo) | 0.1 天 |
| Step 3 (helper + 7 单测) | 0.2 天 |
| Step 4 (公式接通 + 1 单测) | 0.2 天 |
| Step 5 (info + metric + 2 单测) | 0.2 天 |
| Step 6 (debug payload) | 0.15 天 |
| Step 7 (diag calibrate 视实测) | 0.1-0.4 天 |
| Step 8 (文档) | 0.15 天 |
| Step 9 (全量回归 + PR 描述) | 0.1 天 |
| **合计** | **~1.3-1.6 天** |

## AC 验收状态（PR 描述用，待勾选）

- [ ] AC1：`detect_cross_domain_resonance(dominant_axes=[])` 返回 `(0.0, [])`
- [ ] AC2：单 bridge 锁底（top=0.5, sec=0.5 ⇒ resonance=0.5; balance=1.0）
- [ ] AC3：阈值边界锁底（top=0.5, sec=0.04 ⇒ co_act≈0.141 < 0.15 ⇒ 0）
- [ ] AC4：多 bridge 求和锁底（[0.5,0.4,0.3] ⇒ ≈0.834）
- [ ] AC5：`enabled=False` ⇒ `_resolve_dynamic_boost_with_world` 输出与 Phase 2b-1 完全一致
- [ ] AC6：`enabled=True` ⇒ dynamicBoostFactor 按 `× (1 + log(1+resonance))` 缩放
- [ ] AC7：默认 strategy=constant + resonance_enabled=false ⇒ 8 eval suite + invariance + 全部单测全绿
- [ ] AC8：`enabled=true` 在 hashing fixture 上 D2 阈值仍 PASS（必要时重 calibrate post_scale）
- [ ] AC9：2 个 metric spike-on 调用后实际写入 + 单测锁底
- [ ] AC10：search_debug_payload.tag_boost_debug 包含 cross_domain_bridges 当且仅当 enabled=true 且 trigger
- [ ] AC11：README + docs/wave-phase1-architecture.md 落盘
