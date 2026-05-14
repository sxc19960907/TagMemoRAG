# Implement — 检索质量回归测试集

执行清单按依赖序排列。每一步都是可独立 commit 的小切片；遇到失败先回到上一个绿色点再继续。

## 前置检查（开始前）

- [x] 已读 `prd.md` 的 D1-D5 决策与 5 项 MVP 工作项（M1-M5）
- [x] 已读 `design.md` 的模块边界与数据契约
- [x] 当前分支干净，跑一次 `pytest` 全绿建立 baseline
- [x] 确认 `tests/e2e/test_eval_cli.py` 的两个 suite 现状跑通

## 执行清单（按依赖序）

### Step 1: Negatives 字段 + matching + runner（M2 上半）

- [x] 1.1 `eval/dataset.py` 增加 `EvalCase.negatives: tuple[ExpectedRelevance, ...] = ()`，复用 `_parse_relevance_list`
- [x] 1.2 `eval/matching.py` 新增 `match_negatives(results, negatives) -> list[NegativeHit]` 与 `NegativeHit` dataclass
- [x] 1.3 `eval/runner.py`：在每个 case 处理时调 `match_negatives`，把违规打入 `failures`，设置 case `passed=False`
- [x] 1.4 `eval/report.py`：case 报告新增 `negative_hits` 字段
- [x] 1.5 写 `tests/unit/test_eval_negatives.py`：负例命中、负例未命中、多负例、向后兼容（无 negatives 字段的 case）
- [x] 1.6 跑 `pytest tests/unit/test_eval_negatives.py tests/unit/test_eval_runner.py tests/unit/test_eval_matching.py tests/unit/test_eval_dataset.py` 全绿

**Validation**: 上述测试全绿
**Review gate**: 老 case 加载行为零变更（`test_eval_dataset` 不退化）

### Step 2: Fixture 扩展（M1）

按 6 类各 5-6 个 case 编写。每个文件 jsonl 格式，schema 与现有 `coffee.jsonl` 一致。

- [x] 2.1 `tests/fixtures/eval/fault_codes.jsonl`：5 case，覆盖 4 KB 的故障码（含 1 个 negative 跨 KB）
- [x] 2.2 `tests/fixtures/eval/mixed_language.jsonl`：5 case 中英混合 query
- [x] 2.3 `tests/fixtures/eval/model_numbers.jsonl`：5 case 模型号精确召回
- [x] 2.4 `tests/fixtures/eval/tag_cooccurrence.jsonl`：5 case query 触发 ≥2 tag（每个 case 必须列出预期同时活跃的 tag 名）
- [x] 2.5 `tests/fixtures/eval/cross_kb_negatives.jsonl`：5 case 强 negative — query 应在 KB-A 但 negative 期望排除 KB-B 内容
- [x] 2.6 `tests/fixtures/eval/tag_rerank_edge.jsonl`：5 case 向量弱 / tag 强的边缘场景
- [x] 2.7 跑 `tagmemorag eval run` 对每个新 suite，用 hashing 跑通；记录初始 metric 值（不设 suite-level threshold）
- [x] 2.8 跑 `pytest`（含 e2e）全绿，无回归

**Validation**: 6 个新 suite 全部 case 个体通过 case-level 阈值；总 case 数 ≥50
**Review gate**: 反例 case 中故意构造的 "wrong KB query" 在 hashing 下 negative_hits 为空（即 hashing 自然不会命中错误 KB）

### Step 3: Baseline 脚本（M3）

- [x] 3.1 `scripts/build_eval_baseline.py`：parse arg `--embedder hashing|siliconflow` `--output <path>`，跑所有 suite，输出 baseline JSON（design 数据契约）
- [x] 3.2 `_config_hash` 实现：sha256 over (embedder kind + dim + parser config + search config + sorted suite mtimes)
- [x] 3.3 用 hashing 跑生成 `tests/fixtures/eval/baselines/hashing.json`
- [x] 3.4 验证确定性：再跑一次，diff 输出（仅 captured_at 应有不同；所有 metric 字节相等）
- [x] 3.5 接 runner：`tagmemorag eval run` 增加 `--baseline <path>` 选项，加载后给 suite 应用 baseline-2% threshold
- [x] 3.6 写 `tests/unit/test_eval_baseline.py`：加载 baseline → 验证 threshold 计算正确 → suite-level fail 路径

**Validation**: hashing.json 跑两次字节一致（除 captured_at 外）；test_eval_baseline 通过
**Review gate**: AC6 — `scripts/build_eval_baseline.py` 输出确定性

### Step 4: CI workflow（M4）

- [x] 4.1 写 `scripts/run_eval_ci.py`：加载 hashing.json，对每个 suite 跑 `run_eval`，任意 fail 则 exit 1，输出可读报告
- [x] 4.2 `.github/workflows/quality.yml`：trigger pull_request + push to master；steps 按 design 列表
- [x] 4.3 本地用 `act` 或在分支 push 上验证 workflow 跑通（如果环境不支持 act，跳过本地验证，开 PR 后看 GitHub UI）
- [x] 4.4 故意改 fault_codes.jsonl 一条 case 让它必 fail，push 验证 CI 红 → revert
- [x] 4.5 README 增加 "Quality CI" 段，≤30 行

**Validation**: AC4 — PR 上 CI ✓；故意破坏的 case CI ✗
**Review gate**: workflow.yml 不依赖 secret（hashing 不需要），不触发 SiliconFlow

### Step 5: SiliconFlow sanity 脚本 + 文档（M5）

- [x] 5.1 `scripts/eval-siliconflow.sh`：检查 `SILICONFLOW_API_KEY` 存在 → 调 build_eval_baseline.py 跑 siliconflow → 输出 `baselines/siliconflow.json`
- [x] 5.2 本地（如有 API key）跑一次，提交 siliconflow.json 初版
- [x] 5.3 `docs/eval-baseline-workflow.md`：何时重跑 baseline、如何 review 漂移、双 embedder 差异处理
- [x] 5.4 README "Quality CI" 段加 SiliconFlow 本地 sanity 链接

**Validation**: 脚本可执行；docs 描述清晰
**Review gate**: 不在 CI 跑 SiliconFlow（保持 hashing-only CI）

### Step 6: 回归 + 验收

- [x] 6.1 跑 `pytest`（全套），全绿
- [x] 6.2 跑全部 8 个 suite （2 旧 + 6 新）通过 hashing baseline -2% threshold
- [x] 6.3 故意触发 negative 命中验证 AC5
- [x] 6.4 故意删 baselines/hashing.json，跑 `scripts/run_eval_ci.py` 确认 fail
- [x] 6.5 PR 描述附 8 个 AC 勾选状态

**Validation**: AC1-AC8 全部勾选
**Review gate**: 人工 review 整个 PR，重点看 fixture 质量（人工策划质量是 Phase 1 信号可信度的根基）

## 验收命令汇总

```bash
# 单测
pytest tests/unit/test_eval_negatives.py
pytest tests/unit/test_eval_baseline.py
pytest tests/unit/test_eval_*.py

# baseline
uv run python scripts/build_eval_baseline.py --embedder hashing --output tests/fixtures/eval/baselines/hashing.json

# 跑全部 suite
for suite in tests/fixtures/eval/*.jsonl; do
  uv run tagmemorag eval run --suite "$suite" --docs tests/fixtures --config /tmp/hashing.yaml --output /tmp/report.json
done

# 模拟 CI
uv run python scripts/run_eval_ci.py

# 全套
pytest
```

## Review Gates

每个 Step 末尾 review gate 不通过就不进入下一步。设计原则：
1. **Step 1 完成后**：负例 schema 是后面所有 fixture 的前提，先把代码改稳
2. **Step 2 完成后**：fixture 质量是 baseline 数值的来源，劣质 fixture 进 baseline 后污染所有 Phase 1 决策；这一步**慢一点没关系**
3. **Step 3 完成后**：baseline 是 CI 门的唯一数据源；不确定就重跑

## Rollback Points

按倒序 git revert：
1. Step 6 → 文档/AC 描述变更，无影响
2. Step 5 → 删 SiliconFlow 脚本/docs，主流程不动
3. Step 4 → 删 .github/，回到本地手跑
4. Step 3 → 删 baselines/，runner 用现有 case-level threshold
5. Step 2 → 删新 fixture，case 数回到 21
6. Step 1 → 删 negatives schema 支持，回到老 EvalCase

## 工作量估计

| Step | 估时 |
|---|---|
| Step 1 (negatives 代码) | 0.5 天 |
| Step 2 (30 case 人工策划) | 0.5-1 天（瓶颈在 fixture 质量） |
| Step 3 (baseline 脚本 + runner 集成) | 0.5 天 |
| Step 4 (CI workflow) | 0.5 天 |
| Step 5 (SiliconFlow + docs) | 0.5 天 |
| Step 6 (回归 + 验收) | 0.5 天 |
| **合计** | **3-4 天** |

## AC 验收状态（PR 描述用）

- [x] AC1：8 个 jsonl suite 全跑通 baseline -2% threshold（2 旧 + 6 新；case 总数 51 = 7+14+5×6）
- [x] AC2：`tests/unit/test_eval_negatives.py` 9 个用例覆盖 negative 字段解析、matching 命中、runner 失败聚合
- [x] AC3：`tests/fixtures/eval/baselines/hashing.json` 提交并被 `scripts/run_eval_ci.py` 加载；删除文件后 CI exit 1（已本地复现）
- [x] AC4：`.github/workflows/quality.yml` 在 PR 触发；故意把 fault_codes 一条 case 的 source_file/header 改坏 → CI exit 1（已本地复现）
- [x] AC5：构造 negative 在 top-K 命中的 case，runner 输出 `failures` 含 `"negative #X matched at rank Y (file)"`（test_runner_marks_case_failed_when_negative_matches 锁定）
- [x] AC6：`scripts/build_eval_baseline.py` 跑两次，hashing.json 除 captured_at 外字节一致（jq diff 验证 exit 0）
- [x] AC7：README "Quality CI" 段共 26 行；`docs/eval-baseline-workflow.md` 描述 baseline 重跑触发条件、review 流程、failure modes 表格
- [x] AC8：`pytest` 全套 274 通过（无新依赖：本任务只用 hashlib/json/argparse 标准库）
