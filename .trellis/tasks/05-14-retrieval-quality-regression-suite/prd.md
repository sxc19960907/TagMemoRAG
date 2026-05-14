# 检索质量回归测试集 (Phase 1 前置)

## Goal

为 Phase 1（共现矩阵 + V6 spike propagation）建立可信的检索质量回归信号。Phase 0 用 `tests/e2e/test_search_baseline_invariance.py` 锁住 byte-equality；Phase 1 开始要让 search 路径**真正读 tag 表**，byte-equality 不再适用。本任务交付一个 ~50 cases 的 eval suite + GitHub Actions CI 门 + baseline 数值，作为 Phase 1+ 唯一的质量护栏。

## Background / Known Context

### 现有 eval 框架
- `src/tagmemorag/eval/` 已有 `runner.run_eval` / `metrics.compute_ranking_metrics` / `matching.match_expectations` / `dataset.load_eval_suite` / `report` 五件套
- 支持 case-level 和 suite-level 阈值（`min_precision_at_k / min_recall_at_k / min_mrr / min_hit_at_k`）
- CLI: `tagmemorag eval run --suite <jsonl> --docs <dir> --config <yaml> --output <report.json>`
- 现有 fixtures：`tests/fixtures/eval/coffee.jsonl` (7 cases) + `tests/fixtures/eval/product_manuals.jsonl` (14 cases)
- 现有 e2e：`tests/e2e/test_eval_cli.py` 跑两个 suite，硬编码 `assert summary.passed`

### 现有 fixtures 的覆盖盲点
- 只有 happy path：query → 应返回 X，无"不应该返回 X"
- tag 共现场景缺：fixture 平均每 manual 1-2 个 tag，无法刻意构造 "tag-A AND tag-B" 检验 Phase 1 共现矩阵
- 多语言混合 query 少（只有 coffee 部分中文）
- 无 noise query / 模糊匹配 / 模型号精确召回的 stress case
- 无量化 baseline：阈值都是 case-level 0.5/0.1，suite-level 没人显式跑过看现状

### CI 现状
- 项目无 `.github/workflows/`
- 测试只能本地 `uv run pytest` 手跑

### Embedder 选型
- 默认配置：`BAAI/bge-small-zh-v1.5` 走 SiliconFlow HTTP embedding
- CI 友好版：`HashingEmbedder`（dim=64，确定性，无外部依赖）
- `tests/e2e/test_eval_cli.py` 已用 hashing 跑通

## Resolved Decisions

### D1（已锁定）：Suite 规模 = ~50 cases，6 类铺开
新增 ~30 case 按以下分类，每类 5-6 case：
1. **fault-code 精确召回**：E05 / E21 / F07 / 蜂鸣码 / 报警代码（4 个 KB）
2. **中英混合 query**："冰箱 noise loud humming" / "washer drainage 排水"
3. **模型号精确召回**：NRK6192 / WM8 等型号的精确返回
4. **多 tag 共现 query**：故意触发 ≥2 个 tag 同时活跃（Phase 1 共现矩阵的目标场景）
5. **反例 (negatives)**：query 应返回 KB-A 但不应返回 KB-B 的内容
6. **tag-rerank 受益场景**：query 在向量空间不强但 tag 信号强的边缘 case

### D2（已锁定）：CI = GitHub Actions，跑 hashing
- 新建 `.github/workflows/quality.yml`，PR + push to master 触发
- 跑 `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py` + `uv run tagmemorag eval run` 各 suite
- 用 hashing embedder（确定性、无网络、无 API key）
- 阈值不达标 → workflow fail

### D3（已锁定）：Baseline = 当前实现-2%
- 用 hashing embedder 跑当前 master 的 50 cases，记录四个 suite-level 指标的实际值
- 把 suite-level threshold 设到 `floor(baseline - 0.02)`，下限不低于现有 case-level 阈值
- 数值固化在 `tests/fixtures/eval/baselines/hashing.json` 一个版本化文件里
- Phase 1 改动 search 路径若 fail，需明确说明是 regression 还是 baseline 重新校准（再走 review）

### D4（已锁定）：Negatives 字段硬拦截
- 在 case schema 增加可选字段 `negatives: list[ExpectedRelevance]`，复用 relevant 的匹配 schema
- runner / matching 增加：如果 negatives 中任一规则匹配到 top-K 任意结果，case fail（与 metrics 阈值并列的硬条件）
- case 输出报告中列出哪条 negative 被命中

### D5（已锁定）：Embedder 双轨
- **CI（强制门）**：hashing embedder
- **本地 sanity**：SiliconFlow（BAAI/bge-small-zh-v1.5）。提供 shell 脚本 `scripts/eval-siliconflow.sh`，需 `SILICONFLOW_API_KEY` 环境变量。基线数值同样存档为 `tests/fixtures/eval/baselines/siliconflow.json`，仅作参考，**不阻塞 CI**

## Open Questions

无（所有 Blocking/Preference 都锁定）

## MVP Scope

### M1. Fixture 扩展（21 → ~50 cases）
- 按 D1 六类各 5-6 case，新增 ~30 cases
- 文件结构：保留现有 `coffee.jsonl` / `product_manuals.jsonl` 不动；新增同目录文件按分类拆：
  - `fault_codes.jsonl`
  - `mixed_language.jsonl`
  - `model_numbers.jsonl`
  - `tag_cooccurrence.jsonl`
  - `cross_kb_negatives.jsonl`
  - `tag_rerank_edge.jsonl`
- 新分类 case 都带 `min_recall_at_k / min_mrr / min_hit_at_k` 字段（继承现有约定）
- 每个 case 至少 1 个 negative（除 fault_codes 这类极强 query）

### M2. Negatives 字段 + matching 支持
- `eval/dataset.py` 解析 case 的 `negatives` 字段，构造 `ExpectedRelevance` 对象
- `eval/matching.py` 新增 `match_negatives` 函数，返回命中 negatives 的 ranks
- `eval/runner.py` 在 `_threshold_failures` 之外增加 negative-violation 判定，contribute 到 case `failures` 列表
- `eval/report.py` 输出报告增加 `negative_hits: [{rank, negative_index, source_file}]` 字段
- 单测覆盖：negative 命中 / 未命中 / 多 negative

### M3. Baseline 数值 + suite-level threshold
- 新建 `scripts/build_eval_baseline.py`：跑所有 jsonl suite，输出 `tests/fixtures/eval/baselines/hashing.json`：
  ```json
  {
    "embedder": "hashing",
    "captured_at": "2026-05-14T...",
    "config_hash": "...",
    "suites": {
      "coffee.jsonl": {"precision_at_k": 0.7, "recall_at_k": 0.9, "mrr": 0.85, "hit_at_k": 0.95}
    }
  }
  ```
- runner 加载 baseline.json 时，自动给 suite 应用 -2% threshold
- 给 SiliconFlow 同样跑一次（本地脚本）输出 `siliconflow.json`，提交但不参与 CI

### M4. CI workflow
- `.github/workflows/quality.yml`：
  - trigger: pull_request, push to master
  - steps: checkout → setup-python (3.11) → uv sync --extra dev → pytest（带 ignore perf） → eval run × N suites with hashing thresholds
  - 失败行为：non-zero exit, 在 PR check 上显示
- README 增加 "Quality CI" 简短说明（怎么本地复现 CI 跑）

### M5. 本地 SiliconFlow sanity 脚本
- `scripts/eval-siliconflow.sh`：检查 `SILICONFLOW_API_KEY` 存在 → 用 `config.yaml` 的默认配置 → 跑所有 suite → diff 输出与 `baselines/siliconflow.json`
- 文档放在 `docs/eval-baseline-workflow.md`：何时重跑基线、如何 review baseline 漂移

## Out of Scope（明确不做）

- 自动生成 query（LLM 合成）— 这一轮全部人工策划保证质量
- 长文本 query / RAG 阅读理解 case — 当前 retrieval-only，不评测生成
- 多 KB 跨 KB 召回（需要先实现跨 KB 检索本身，未排期）
- BM25 调参 / lexical_search 单独评测 — 跟 wave 一起算
- nDCG 指标 — 现有 4 个指标（precision/recall/MRR/hit）足够 Phase 1
- eval 性能优化（hashing 跑 50 cases <30s 已可接受）

## Requirements

1. **R1（数据）**：≥50 cases 总量，6 类覆盖，每类 ≥5 个 case
2. **R2（baseline）**：hashing 与 siliconflow 两套 baseline 都有版本化档案
3. **R3（CI）**：GitHub Actions 跑 pytest + hashing eval，PR 触发
4. **R4（negatives）**：case schema + matching + runner 三处支持，单测覆盖
5. **R5（兼容）**：现有 `coffee.jsonl` / `product_manuals.jsonl` schema 不变，case-level 阈值不下调
6. **R6（可重现）**：`scripts/build_eval_baseline.py` 输出确定性（hashing dim=64 + 固定种子）
7. **R7（文档）**：README 加 "Quality CI" 一段；`docs/eval-baseline-workflow.md` 描述 baseline 重跑流程

## Acceptance Criteria

- [ ] AC1：`tagmemorag eval run` 全部 jsonl suites 跑通，case 数 ≥50，suite-level 阈值用 baselines/hashing.json -2%
- [ ] AC2：单测 `tests/unit/test_eval_negatives.py` 覆盖 negative 字段解析、matching 命中、runner 打入 failures
- [ ] AC3：`tests/fixtures/eval/baselines/hashing.json` 存在并被 CI 加载；删除该文件 CI fail
- [ ] AC4：`.github/workflows/quality.yml` 在 PR 上触发；故意把 fault_codes.jsonl 一个 case 改成必 fail（如 expected source_file 改成不存在路径），CI fail
- [ ] AC5：构造一个 case 让 negative 在 top-K 内命中，runner 报告 case fail 并在 `negative_hits` 中列出
- [ ] AC6：`scripts/build_eval_baseline.py` 跑两次，hashing.json 字节一致（确定性）
- [ ] AC7：README "Quality CI" 段不超过 30 行；`docs/eval-baseline-workflow.md` 描述 baseline 重跑触发条件、review 流程
- [ ] AC8：`pytest` 全套不退化，不引入新依赖（保持 dev extras 不变）

## Definition of Done

- 6 个新 fixture 文件 + ≥30 个新 case 落盘
- `eval/dataset.py` / `eval/matching.py` / `eval/runner.py` / `eval/report.py` 改完，单测通过
- `scripts/build_eval_baseline.py` + `scripts/eval-siliconflow.sh` 可执行
- `.github/workflows/quality.yml` 跑通至少一次（PR 上看到 ✓）
- 两套 baseline 文件各自存档，README + docs 文档更新
- 全套 pytest 绿

## Decision Log (ADR-lite)

- **D1**: Suite 50 cases，6 分类各 5-6 个
- **D2**: CI = GitHub Actions，跑 hashing
- **D3**: Suite-level threshold = baseline - 2%
- **D4**: Negatives 字段硬拦截
- **D5**: 双 embedder 策略：CI hashing + 本地 SiliconFlow sanity
