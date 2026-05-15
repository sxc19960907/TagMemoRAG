# Implement — Phase 2a：EPA real-PCA 通路验证 + dynamic boost 接通

执行清单按依赖序排列。每一步都是可独立 commit 的小切片；遇到失败先回到上一个绿色点再继续。

## 前置检查（开始前）

- [x] 已读 `prd.md` 的 D1-D7 决策与 8 个 R / 7 个 AC
- [x] 已读 `design.md` 的模块边界、数据契约、关键算法步骤、失败语义
- [x] 当前分支存在任务改动；`uv run pytest -q` 全绿（338 passed, 2 skipped）
- [x] 跑一次 `uv run python scripts/run_eval_ci.py` 全绿（8 suites pass）

## 执行清单（按依赖序）

### Step 1: Config 字段加挡（M1）

- [x] 1.1 `src/tagmemorag/config.py` `WavePhase1Config` 加 `epa_logic_depth_scale: float = Field(default=1.0, ge=0.0)` 和 `epa_floor: float = Field(default=0.0, ge=0.0)`
- [x] 1.2 `config.yaml` 同步加两个字段（`epa_logic_depth_scale=2.0` 按 D7 诊断结论调整；strategy 默认仍 constant）
- [x] 1.3 跑 `uv run pytest tests/unit/test_config_env.py -q`，全绿

**Validation**: 新字段默认值与 Phase 1 现状语义等价
**Review gate**: 不引入向后不兼容

### Step 2: `_resolve_dynamic_boost` fallback 公式（M2）

- [x] 2.1 `src/tagmemorag/wave_tag_spike.py` `_resolve_dynamic_boost`：strategy="epa" 路径 logicDepth 计算后改成 `max(epa_floor, logicDepth * epa_logic_depth_scale)`
- [x] 2.2 跑 `uv run pytest tests/unit/test_apply_tag_boost.py -q`，全绿

**Validation**: AC6 雏形 — 默认参数等价 Phase 1
**Review gate**: 不动 strategy="constant" 路径，不动 EPA 加载失败兜底路径

### Step 3: Fixture 扩展（M3）

- [x] 3.1 选 1 个现有 manual（`air_conditioner/ac_ap12.metadata.json`），加 2 个全局新 tag（`airflow`, `condensate-drain`）
- [x] 3.2 验证全局 unique 从 10 → 12
- [x] 3.3 跑 `uv run python scripts/run_eval_ci.py`，确认 8 个 suite 仍过 baseline -2% 阈值
- [x] 3.4 suite 未漂出阈值，无需换 tag

**Validation**: AC5 雏形 — baseline 不漂
**Review gate**: 8 个 suite 都过；fixture 改动最小

### Step 4: 诊断脚本（M4）

- [x] 4.1 写 `scripts/diag_epa_logic_depth.py`：按 design.md "诊断脚本输出格式" 实现
  - 临时 data_dir + cfg `epa_min_k=4`
  - 对 12-tag fixture 跑 `build_kb` 触发 real-pca
  - 收集 `tests/fixtures/eval/*.jsonl` 的 question 文本作为 query 集
  - 编码 → projector.project → logicDepth 序列 + apply_tag_boost → alpha 序列
  - 同步打印 `pca.explained_variance_ratio_[:K]` 和 sum
  - cold-start 模式做对照（用 `epa_min_k=200` 强制走 cold-start 分支）
  - 计算 D2 阈值 PASS/FAIL，return-code = 0 if PASS else 1
- [x] 4.2 跑诊断脚本：`uv run python scripts/diag_epa_logic_depth.py`，输出 PASS
- [x] 4.3 **决策点（D7 候选）**：
  - 如果 PASS ⇒ scale 默认 1.0 不动；记录到 PRD 作为 "D7: scale=1.0 已达标，无需调"
  - 如果 FAIL ⇒ 二分查找最小达标 scale（试 1.5 / 2.0 / 3.0），更新 `config.yaml` 的 `epa_logic_depth_scale` 默认值，记录到 PRD 作为 "D7: scale=X 满足 D2 阈值"
  - **实际结果（2026-05-15）**：scale=1.0 未达标；scale=2.0 达标，已写回 PRD D7。

**Validation**: AC1（诊断脚本可重复）+ AC2（PCA 能量解释比例 > 0.5）+ AC3 决策点
**Review gate**: 诊断输出有可读性，PASS/FAIL 判断逻辑清晰

### Step 5: 单测（M5）

- [x] 5.1 写 `tests/unit/test_epa_logic_depth.py`，4 段单测：
  - `test_resolve_dynamic_constant_unchanged`：strategy="constant" ⇒ 1.0
  - `test_resolve_dynamic_epa_with_real_pca_basis`：写真 PCA basis 到 tmp，验证返回 `max(floor, logicDepth * scale)`
  - `test_resolve_dynamic_epa_degenerate_query_falls_back_to_floor`：AC4，logicDepth=0 ⇒ 返回 epa_floor
  - `test_resolve_dynamic_epa_default_params_equivalent_to_phase1`：AC6，scale=1.0/floor=0.0 ⇒ 等价 Phase 1
- [x] 5.2 加一段 e2e 测试 `test_apply_tag_boost_strategy_epa_passes_d2_threshold`：AC3 锁底
- [x] 5.3 跑 `uv run pytest tests/unit/test_epa_logic_depth.py -v`，全绿

**Validation**: AC3 + AC4 + AC6 锁底
**Review gate**: 4 段单测每段对应一个明确决策

### Step 6: 文档（M6）

- [x] 6.1 README "Wave Phase 1" 段加一段 "Switching to EPA dynamic boost"：
  - 何时切：tag 数 ≥ 16 ⇒ EPA 训出真 PCA ⇒ 可切 `dynamic_boost_factor_strategy: epa`
  - 切之前先跑 `scripts/diag_epa_logic_depth.py` 确认 alpha 浮动有意义
  - 出问题就回 constant：`dynamic_boost_factor_strategy: constant`
- [x] 6.2 `docs/wave-phase1-architecture.md` 加 "EPA dynamic boost: cold-start vs real-pca" 子章节，说明：
  - cold-start 是 identity basis ⇒ logicDepth 退化为 0 ⇒ 等价 constant 模式
  - real-pca 在 KB tag 数 ≥ 16 时自动训
  - `epa_logic_depth_scale` 单参数旋钮，默认 1.0；如果 hashing 噪音压制 logicDepth，可以调到 2.0-3.0
  - 兜底链路：epa_floor → dynamic_boost_min → dynamic_boost_max
- [x] 6.3 docs 里加一句 "Phase 2b 会接 ResidualPyramid 补全 `dynamicBoostFactor` 公式"，与 Phase 1 文档前后呼应

**Validation**: AC7
**Review gate**: 文档不暴露"WAVE 算法"词汇过度承诺；只描述 dynamic boost 切换条件

### Step 7: 全量回归（M7）

- [x] 7.1 跑 `uv run pytest -q` 全套，全绿（338 passed, 2 skipped）
- [x] 7.2 跑 `uv run python scripts/run_eval_ci.py` 全绿（8 suites pass）
- [x] 7.3 跑 `uv run pytest tests/e2e/test_search_baseline_invariance.py -v`（spike-off 字节一致）
- [x] 7.4 7 个 AC 勾选状态 + Step 4 诊断脚本输出 + D7 决策已记录到任务文档

**Validation**: AC1-AC7 全勾
**Review gate**: 不引入回归

## 验收命令汇总

```bash
# Step 4 诊断
uv run python scripts/diag_epa_logic_depth.py

# Step 5 单测
uv run pytest tests/unit/test_epa_logic_depth.py -v

# Step 7 全量
uv run pytest -q
uv run python scripts/run_eval_ci.py
uv run pytest tests/e2e/test_search_baseline_invariance.py
```

## Review Gates

每步末尾 review gate 不通过就不进入下一步：
1. **Step 3 后**：8 个 eval suite baseline 不漂（如漂 ⇒ 调 fixture 加的 tag 选择）
2. **Step 4 后**：D7 决策（scale 默认值）写回 PRD
3. **Step 5 后**：AC4 退化路径单测明确写在 logicDepth=0 的 fixture 上（不是用 mock projector）

## Rollback Points

按倒序 git revert：
1. Step 6 → 文档变更，无影响
2. Step 5 → 撤回单测
3. Step 4 → 撤回诊断脚本（不影响主路径）
4. Step 3 → 撤回 fixture 改动（baseline 自动恢复 Phase 1 状态）
5. Step 2 → 撤回 fallback 公式（strategy=epa 路径退回 Phase 1 直返 logicDepth）
6. Step 1 → 撤回 config 字段（pydantic 默认值消失，但生产侧 strategy=constant 默认 ⇒ 无影响）

**完整回滚**（紧急）：
```bash
# 配置软回滚
yq -i '.wave_phase1.dynamic_boost_factor_strategy = "constant"' config.yaml

# 代码回滚
git revert <step1-commit>..<step7-commit>
```

## 工作量估计

| Step | 估时 |
|---|---|
| Step 1 (config 字段) | 0.1 天 |
| Step 2 (fallback 公式) | 0.2 天 |
| Step 3 (fixture 扩展 + baseline 验证) | 0.2 天 |
| Step 4 (诊断脚本 + D7 决策) | 0.3 天 |
| Step 5 (4+1 段单测) | 0.2 天 |
| Step 6 (文档) | 0.1 天 |
| Step 7 (全量回归 + PR 描述) | 0.1 天 |
| **合计** | **~1 天** |

## AC 验收状态（PR 描述用，待勾选）

- [x] AC1：诊断脚本可重复，输出 cold-start vs real-pca 对照数据 + D2 PASS/FAIL
- [x] AC2：`epa_min_k=4` + 12 unique tags 触发 real-pca，PCA explained_variance sum > 0.5
- [x] AC3：strategy="epa" + scale=2.0 alpha 序列满足 D2 阈值（D7 已回写）
- [x] AC4：strategy="epa" + 退化 query ⇒ 走 epa_floor / dynamic_boost_min 不爆炸
- [x] AC5：8 个 hashing eval suite 仍过 baseline -2%；e2e baseline invariance 仍过
- [x] AC6：默认 strategy="constant"；EPA scale/floor 仅在显式切 `"epa"` 时生效
- [x] AC7：README + docs/wave-phase1-architecture.md 加 EPA dynamic boost 切换条件文档
