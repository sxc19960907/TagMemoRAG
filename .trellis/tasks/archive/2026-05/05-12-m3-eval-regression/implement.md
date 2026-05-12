# implement.md — M3 质量回归实施 checklist

> 原则：先做纯函数和离线 runner，再接 CLI。每一步都能用小测试验证，避免把 eval 变成一坨只能端到端调的脚本。

---

## Phase A — 契约与 fixture

- [x] **A1** 新建 `src/tagmemorag/eval/` package。
- [x] **A2** 定义 `ExpectedResult / EvalCase / EvalThresholds` 数据结构。
- [x] **A3** 实现 JSONL loader，包含 line number 错误信息。
- [x] **A4** 标注项支持可选 `relevant[].id`；report 中无 id 时生成 `<case_id>#<index>`。
- [x] **A5** 新增 `tests/fixtures/eval/coffee.jsonl`，覆盖当前 coffee fixture 的 3-5 个 query。
- [x] **A6** 写 `tests/unit/test_eval_dataset.py`，覆盖 duplicate id、empty relevant、missing matcher field、invalid threshold。

**验证**：

```bash
uv run pytest tests/unit/test_eval_dataset.py -v
```

---

## Phase B — 匹配与指标

- [x] **B1** 实现 expectation/result matching。
- [x] **B2** 实现 `precision_at_k / recall_at_k / mrr / hit_at_k`。
- [x] **B3** 实现 macro aggregate summary。
- [x] **B4** 固定浮点输出格式或统一 JSON 数值精度策略。
- [x] **B5** `source_file` 默认按 stored value 精确匹配；basename fallback 只能在唯一候选时通过，歧义时报数据错误。
- [x] **B6** 写 `tests/unit/test_eval_matching.py` 和 `tests/unit/test_eval_metrics.py`。

**验证**：

```bash
uv run pytest tests/unit/test_eval_matching.py tests/unit/test_eval_metrics.py -v
```

---

## Phase C — Runner 与 report

- [x] **C1** 实现 `EvalReport / EvalCaseReport / EvalSummary`。
- [x] **C2** 实现 `run_eval(...)`：按 KB 分组，一次 build/load，多 query 搜索。
- [x] **C3** 默认 docs-based eval 派生临时 `storage.data_dir`（例如 `.tmp/eval/<run_id>`），避免读取或写入主 `data/{kb_name}`。
- [x] **C4** 支持 `--reuse-built-kb` 对应的 runner 参数；只有该模式读取配置中的正常 storage。
- [x] **C5** report 包含 summary、thresholds、case metrics、actual top-k、eval storage snapshot。
- [x] **C6** 阈值失败不抛异常；返回 `passed=false`，由 CLI 决定 exit code。
- [x] **C7** case-level 阈值作为 suite-level gate 之外的额外约束。
- [x] **C8** 写 runner 单元或集成测试，确认默认 eval 不污染主 storage。

**验证**：

```bash
uv run pytest tests/unit/test_eval_runner.py -v
```

---

## Phase D — CLI 集成

- [x] **D1** 在 `src/tagmemorag/cli.py` 增加 `eval run` 子命令。
- [x] **D2** 参数包括 `--suite / --docs / --config / --output / --top-k / --kb / --reuse-built-kb / --eval-data-dir / --min-*`。
- [x] **D3** CLI 通过时退出 `0`，阈值失败退出 `1`，参数/数据错误退出 `2`。
- [x] **D4** stdout 输出简洁 summary，详细内容写 JSON report 或 stdout。
- [x] **D5** 默认门禁为 `recall@k / mrr / hit@k`；`precision@k` 默认只报告，只有显式 `--min-precision-at-k` 时参与 gate。
- [x] **D6** 捕获 eval suite/data/runtime 用户错误并返回 `2`，不要输出 traceback。
- [x] **D7** 写 `tests/e2e/test_eval_cli.py` 覆盖通过、阈值失败、临时 storage 隔离。

**验证**：

```bash
uv run pytest tests/e2e/test_eval_cli.py -v
```

---

## Phase E — 文档与 CI 门禁

- [x] **E1** README 增加 `Quality Eval` 章节。
- [x] **E2** 文档说明 JSONL 标注格式、如何新增 query、如何解读 report。
- [x] **E3** 文档给出本地 gate 命令。
- [x] **E4** 说明默认 gate 使用 `recall@k / mrr / hit@k`，precision 是诊断指标或显式 opt-in gate。
- [x] **E5** 检查 `.github/workflows` 是否已有 CI；如果有，添加 deterministic eval gate。
- [x] **E6** 如果没有 CI，记录推荐命令，不额外引入 CI 框架。

**验证**：

```bash
uv run pytest tests/ -v
uv run tagmemorag eval run --suite tests/fixtures/eval/coffee.jsonl --docs tests/fixtures --config config.yaml --output .tmp/eval-report.json
```

---

## Review Gates

- [x] PRD/design/implement 已确认，且没有把 M4/post-v1 内容塞进 M3。
- [x] 标注格式能被 code review 直接看懂。
- [x] 默认 eval 不依赖网络、不下载模型。
- [x] 默认 eval 使用隔离 storage，不读取或写入主 `data/{kb_name}`。
- [x] 默认 CI gate 不使用不适合小 fixture 的 `precision@5 >= 0.8` 硬阈值。
- [x] 阈值失败的输出足够定位具体 query 和 top-k 实际结果。
- [x] 现有 M0-M2 测试全部保持通过。

---

## Estimated Effort

| Phase | 估时 | 累计 |
|-------|------|------|
| A 契约&fixture | 0.5d | 0.5d |
| B 匹配&指标 | 0.75d | 1.25d |
| C Runner&report | 1d | 2.25d |
| D CLI | 0.75d | 3d |
| E 文档&CI | 0.5d | 3.5d |

**M3 总计约 3.5 人日**。如果要加入真实模型 profile 或 GitHub Actions 细化，另加 0.5-1d。

---

## Rollback Points

- Phase A/B 失败：只保留 metric 纯函数和 loader 草稿，不接 CLI。
- Phase C 失败：先保留 `run_eval` 手动调用，不做门禁。
- Phase D 失败：回退 CLI 子命令，保留 Python API。
- Phase E 失败：不接 CI，只记录本地命令。

---

## Out of Scope

- Prometheus metrics / OTel traces → M4
- HTTP eval runner → post-v1 或 M4 联调时再做
- LLM-as-judge → post-v1
- 大规模标注管理平台 → post-v1
- 真实模型 eval 默认进 CI → post-v1/nightly
