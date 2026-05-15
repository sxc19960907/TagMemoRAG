# Implement — Phase 1：共现矩阵 + V6 spike propagation

执行清单按依赖序排列。每一步都是可独立 commit 的小切片；遇到失败先回到上一个绿色点再继续。

## 前置检查（开始前）

- [ ] 已读 `prd.md` 的 D1-D5 决策与 7 个 MVP 块
- [ ] 已读 `design.md` 的模块边界、数据契约、关键算法步骤
- [ ] 已读 `research/source-cooccurrence-matrix.md` 的 phi 公式 + legacy fallback
- [ ] 已读 `research/source-tag-boost-and-spike.md` 的 V6 spike 完整流程
- [ ] 当前分支干净，跑一次 `pytest` 全绿建立 baseline
- [ ] 跑一次 `scripts/run_eval_ci.py` 全绿（确认 Phase 1 前的 baseline 起点）

## 执行清单（按依赖序）

### Step 1: Cooccurrence matrix builder（M1）

- [ ] 1.1 写 `src/tagmemorag/tag_cooccurrence.py`：`CooccurrenceMatrix` dataclass + `build_cooccurrence_for_kb` + `save_cooccurrence` + `load_cooccurrence`
- [ ] 1.2 atomic write（tmp → fsync → replace → fsync(dir)）— 复用 `epa_basis._atomic_write_npz` 模式（如该 helper 已抽出则直接复用，否则就地实现）
- [ ] 1.3 写 `tests/unit/test_tag_cooccurrence.py`：phi 公式 4-tag fixture、direction asymmetric (n=2)、legacy fallback 双向、cap n>100 跳过、empty kb 不写文件、roundtrip save/load
- [ ] 1.4 跑 `pytest tests/unit/test_tag_cooccurrence.py`，全绿
- [ ] 1.5 跑 `pytest`（全套）确认无回归

**Validation**: AC2 + AC6（确定性）+ AC7（缺文件不爆炸）单测覆盖
**Review gate**: phi 公式与 source-cooccurrence-matrix.md 第 §"phi(pos, n) formula" 段字节一致

### Step 2: Spike propagation 算法（M2）

- [ ] 2.1 写 `src/tagmemorag/wave_tag_spike.py` 的 `propagate(seed_weights, matrix, residuals, **constants) -> SpikeResult`
- [ ] 2.2 严格按 `research/source-tag-boost-and-spike.md` § [4.5] 实现：active spikes Map、accumulated energy Map、wormhole gate、neighbor sort/cap、emergent cap
- [ ] 2.3 写 `tests/unit/test_wave_tag_spike_propagate.py`：3-node chain 解析期望（AC3）、wormhole gate 触发（AC8）、neighbor cap 触发、emergent cap 触发、empty seeds、empty matrix、firing threshold 截断
- [ ] 2.4 跑 `pytest tests/unit/test_wave_tag_spike_propagate.py`，全绿

**Validation**: AC3（3-node chain 算法锁底）+ AC8（wormhole）单测覆盖
**Review gate**: 算法每一步都能回指源代码行号

### Step 3: apply_tag_boost 集成（M3）

- [ ] 3.1 在 `wave_tag_spike.py` 添加 `apply_tag_boost(query_vec, *, kb_name, settings, base_tag_boost) -> (vec, TagBoostInfo)`
- [ ] 3.2 实现 5 个子步：seed selection / propagate / merge+dedup / weighted-mean context / alpha fuse（详见 design.md）
- [ ] 3.3 实现 `_load_matrix_cached`（mtime_ns 作为 cache key，最多 16 项）
- [ ] 3.4 实现 `_select_seeds`（top-K cosine over `iter_canonical_tags_with_vectors`）
- [ ] 3.5 dynamic_boost_factor 双策略：`"constant"` (=1.0) / `"epa"` (走 epa_projector.project)
- [ ] 3.6 写 `tests/unit/test_apply_tag_boost.py`：happy path、matrix_missing 短路、no_seeds 短路、degenerate_context 短路、spike_disabled 短路、constant vs epa 策略
- [ ] 3.7 跑 `pytest tests/unit/test_apply_tag_boost.py`

**Validation**: 上述测试全绿
**Review gate**: 每个 skipped_reason 路径都有专属 case，TagBoostInfo 字段都被覆盖

### Step 4: search_runtime / wave_searcher 接入（M4）

- [ ] 4.1 修改 `wave_searcher.wave_search`：增加 `disable_legacy_tag_boost: bool = False` (kwargs only)；在现有 metadata field boost 段中跳过 tags 维度
- [ ] 4.2 修改 `search_runtime.execute_search`：在 ANN/lexical 之后、wave_search 之前调 `apply_tag_boost`，按 BoostInfo.skipped_reason 决定是否替换 query_vec
- [ ] 4.3 在 `SearchExecution` dataclass 加 `tag_boost_info: TagBoostInfo | None = None`
- [ ] 4.4 修改 `search_runtime._lexical_profile` / debug payload：把 BoostInfo 透传到 debug response（仅当 caller 开 debug）
- [ ] 4.5 写 `tests/unit/test_search_runtime_phase1.py`：spike off 时 query_vec 不变（AC4 雏形）、spike on 时 query_vec 改变、wave_search 收到 disable_legacy_tag_boost=True 时跳过 tags boost、legacy_chunk_tag_boost=true 时回退（AC9）
- [ ] 4.6 跑相关单测全绿

**Validation**: AC4 + AC9 单测覆盖
**Review gate**: spike 旁路 + escape hatch 都打通

### Step 5: Rebuild 生命周期（M5）

- [ ] 5.1 修改 `tag_rebuild.sync_rebuild_tags`：末尾追加 `build_and_save_cooccurrence(kb_name, cfg)` + 报告字段
- [ ] 5.2 在 `tag_rebuild.py` 实现 `build_and_save_cooccurrence` thin wrapper：try/except 抓异常，empty matrix 不写文件，记录 duration
- [ ] 5.3 修改 `state.RebuildTask`：新增 `tag_cooccurrence_edges`/`tag_cooccurrence_error` + to_dict 序列化
- [ ] 5.4 修改 `state._build_for_rebuild` / `incremental_rebuild`：将新字段透传到 RebuildDetail（与 Phase 0 9 个字段同模式）
- [ ] 5.5 写 `tests/unit/test_phase1_rebuild_cooccurrence.py`：fixture build → 验证 npz 落盘 + edges>0、第二次 rebuild edges 不变、构建失败时 error_type 非空但 rebuild 仍 done（AC10）
- [ ] 5.6 跑相关测试

**Validation**: AC10 + 矩阵 atomic write 验证
**Review gate**: rebuild 失败不破坏 search

### Step 6: Config + 可观测 + 文档（M6）

- [ ] 6.1 `config.py` 新增 `WavePhase1Config`，所有 D1-D5 默认值齐全
- [ ] 6.2 `config.yaml` 加 `wave_phase1` 段，spike_enabled: false 默认
- [ ] 6.3 `observability/metrics.py` 加 3 个新指标 + record_* helpers
- [ ] 6.4 写 `tests/unit/test_observability_metrics.py` 加新指标 case
- [ ] 6.5 写 `docs/wave-phase1-architecture.md`：算法概览、kill switch、回滚、调参建议
- [ ] 6.6 README "Tag Data Model" 章节加一段：spike 默认关闭 / 怎么打开 / 与 chunk-side tag_boost 关系

**Validation**: 启动服务 → curl /metrics → 看到新指标
**Review gate**: 文档不暴露"WAVE 算法"词汇过度承诺；只描述数据层 + spike 机制

### Step 7: Baseline 重训（M7）

- [ ] 7.1 临时改 `config.yaml` `spike_enabled: true`，跑 `uv run python scripts/build_eval_baseline.py --embedder hashing --output tests/fixtures/eval/baselines/hashing.json`
- [ ] 7.2 把 `spike_enabled` 改回 `false`
- [ ] 7.3 git diff baseline.json，记录每个 suite 的 metric 变化幅度（写到 PR 描述）
- [ ] 7.4 跑 `scripts/run_eval_ci.py` — 因为 spike 默认关，跑出来仍是 spike-off 路径下的指标，必须能对上 baseline（baseline 是在 spike-on 状态测的，spike-off 状态测的会更低 ⇒ 这里需要决定：CI 跑 spike on 还是 off）

**临时决策点（需在 implement 期回到 PRD 补 D6）**：
- 选项 A：CI 也跑 spike on（修改 `run_eval_ci.py` 让它在子进程中临时设 `WAVE_PHASE1_SPIKE_ENABLED=true` 环境覆盖）
- 选项 B：维持 CI 跑 spike off，spike on 的 baseline 仅作记录、不进 CI 门
- 选项 C：另起一份 baseline `hashing-spike-on.json`，CI 同时跑 off + on 两套阈值

**Step 7 在实施期实际开工前要先决定**。建议选项 A，保证 baseline 与 CI 行为一致。

### Step 8: 回归 + 验收（合并到 Step 7）

- [ ] 8.1 跑 `pytest`（全套），全绿（AC1）
- [ ] 8.2 跑 `tests/e2e/test_search_baseline_invariance.py` (默认 spike off) ⇒ 全过（AC4）
- [ ] 8.3 临时打开 spike，跑 `scripts/run_eval_ci.py`（按 Step 7 选项决定）⇒ 全过（AC5）
- [ ] 8.4 删 `data/_global/tag_cooccurrence/` 重启，跑 search → 不报错（AC7）
- [ ] 8.5 故意把 builder 注入异常（mock），rebuild status="done" 但 error 字段非空（AC10）
- [ ] 8.6 PR 描述附 10 个 AC 勾选状态 + baseline 变化 metric 表

## 验收命令汇总

```bash
# 单测
pytest tests/unit/test_tag_cooccurrence.py
pytest tests/unit/test_wave_tag_spike_propagate.py
pytest tests/unit/test_apply_tag_boost.py
pytest tests/unit/test_search_runtime_phase1.py
pytest tests/unit/test_phase1_rebuild_cooccurrence.py
pytest tests/unit/test_observability_metrics.py

# 全套
pytest

# baseline 重训（spike on）
yq -i '.wave_phase1.spike_enabled = true' config.yaml
uv run python scripts/build_eval_baseline.py --embedder hashing \
  --output tests/fixtures/eval/baselines/hashing.json
yq -i '.wave_phase1.spike_enabled = false' config.yaml

# CI 模拟
uv run python scripts/run_eval_ci.py

# AC4 spike off 字节一致
uv run pytest tests/e2e/test_search_baseline_invariance.py

# AC7 删矩阵后 search 不爆
rm -rf data/_global/tag_cooccurrence/
uv run pytest tests/e2e/test_search_baseline_invariance.py
```

## Review Gates

每步末尾 review gate 不通过就不进入下一步：
1. **Step 1 后**：phi 公式必须 byte-for-byte 对齐源代码。错了后续 spike 全错
2. **Step 2 后**：spike 算法是首次 hand-port 的复杂数值循环；3-node chain 解析期望必须能用纸笔推导核对
3. **Step 7 决策**：CI 跑 spike on 还是 off — 这是产品默认形态的硬选择，定下来后才能跑 baseline

## Rollback Points

按倒序 git revert：
1. Step 8 → 文档/AC 描述变更，无影响
2. Step 7 → 撤回 baseline.json 改动
3. Step 6 → 删 wave_phase1 段、metrics、文档
4. Step 5 → tag_rebuild 不再调 builder；矩阵文件停止生成（不影响已存在文件，可手动删）
5. Step 4 → search_runtime 不再调 apply_tag_boost；query_vec 走老路径
6. Step 3 → 删 apply_tag_boost
7. Step 2 → 删 propagate
8. Step 1 → 删 tag_cooccurrence.py + 数据目录

**完整回滚**（紧急）：
```bash
# 配置软回滚
yq -i '.wave_phase1.spike_enabled = false' config.yaml

# 数据硬回滚
rm -rf data/_global/tag_cooccurrence/

# 代码回滚
git revert <step1-commit>..<step8-commit>
```

## 工作量估计

| Step | 估时 |
|---|---|
| Step 1 (cooccurrence builder + 单测) | 0.5 天 |
| Step 2 (spike propagation 算法 + 单测) | 1 天 |
| Step 3 (apply_tag_boost 集成 + 单测) | 0.5 天 |
| Step 4 (search_runtime / wave_searcher 接入 + 单测) | 0.5 天 |
| Step 5 (rebuild 生命周期 + 单测) | 0.5 天 |
| Step 6 (config + 可观测 + 文档) | 0.5 天 |
| Step 7+8 (baseline 重训 + 回归 + 验收) | 0.5 天 |
| **合计** | **4 天** |

## AC 验收状态（PR 描述用，待勾选）

- [x] AC1：`pytest` 全套通过（332 passed, 2 skipped）
- [x] AC2：4-tag fixture phi 公式输出位元一致（`test_phi_pair_4tag_fixture`）
- [x] AC3：3-node chain spike 一跳后 accumulatedEnergy 与解析期望相等（`test_3node_chain_analytic_expectation`）
- [x] AC4：spike off 时 e2e baseline invariance 全过（`test_search_output_invariant_*`）
- [x] AC5：spike on 时 8 个 eval suite 通过新 hashing baseline -2% 阈值；新 baseline 提交进 PR（`run_eval_ci.py` 全过）
- [x] AC6：rebuild 跑两次 npz 字节一致（除 built_at）（`test_two_consecutive_builds_yield_identical_matrix`）
- [x] AC7：删矩阵后 search 不报错（`test_load_missing_file_returns_none` + `test_skipped_when_matrix_missing` + `test_spike_on_but_matrix_missing_keeps_legacy`）
- [x] AC8：合成 fixture 上 wormhole gate 触发，decay 走 0.70（`test_wormhole_gate_triggers_at_high_tension`）
- [x] AC9：spike on + legacy off 时 wave_searcher 跳过 chunk-side tag boost；legacy=true 时回退（`test_spike_on_invokes_apply_and_disables_legacy` + `test_legacy_chunk_tag_boost_escape_hatch`）
- [x] AC10：rebuild 失败注入测试，rebuild status=done + error_type 非空（`test_builder_failure_does_not_break_rebuild` + `test_recovery_after_failure`）

## Baseline 变化（spike on）

8 个 hashing eval suite 的 metric 数值与 Phase 0 baseline **完全一致**（仅 `captured_at` / `config_hash` 不同）。原因（与 `research/source-tag-boost-and-spike.md` 第 284 行预测一致）：
- `α = base_tag_boost (0.03) * dynamic_factor (1.0) = 0.03`，blend 扰动幅度仅 3%，不足以改变 top-K 排序。
- fixture 规模下 hashing dim=64 噪音 + `seed_min_similarity=0.3` 阈值 ⇒ 多数 query 走 `no_seeds` 短路。
- `legacy_chunk_tag_boost=false` 默认下 chunk-side tag bonus 关闭，与 query-vector blend 此消彼长。

这印证了 D1 的判断：spike 算法接入是干净的"上线即可观测、不冲击数值基线"的状态。Phase 2b 接 ResidualPyramid + EPA real-PCA 后再观察 metric drift。
