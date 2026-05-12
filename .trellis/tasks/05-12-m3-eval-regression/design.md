# design.md — M3 质量回归技术设计

> 约束：本文档只覆盖 M3。M4 观测、真实模型定时评测、Web dashboard 和 LLM-as-judge 不在本任务内。
> 父文档：[prd.md](./prd.md)
> 依赖基座：M0 parser/graph/search/storage/CLI，M1 config/logging，M2 multi-KB/cache/auth 不参与默认 eval 执行链。

---

## 1. 模块边界与改动范围

```
┌────────────────────────────────────────────────────────────┐
│ CLI: tagmemorag eval run                                  │
│  - parse args                                             │
│  - load Settings                                          │
│  - create embedder                                        │
│  - call eval.runner.run_eval                              │
└──────────────────────────────┬─────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────┐
│ tagmemorag.eval                                             │
│  dataset.py  -> load JSONL, validate EvalCase              │
│  matching.py -> decide whether Result matches expectation  │
│  metrics.py  -> precision@k / recall@k / MRR / hit@k       │
│  runner.py   -> build/load KB, run wave_search, report     │
│  report.py   -> dataclasses + JSON serialization           │
└──────────────────────────────┬─────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────┐
│ Existing core                                                │
│  build_kb / load_kb / wave_search / Result                  │
└────────────────────────────────────────────────────────────┘
```

**改动清单**：

| 模块 | 类型 | 摘要 |
|------|------|------|
| `src/tagmemorag/eval/__init__.py` | new | eval package exports |
| `src/tagmemorag/eval/dataset.py` | new | JSONL loader + validation |
| `src/tagmemorag/eval/matching.py` | new | expectation-to-result matching |
| `src/tagmemorag/eval/metrics.py` | new | ranking metrics |
| `src/tagmemorag/eval/report.py` | new | report dataclasses / JSON |
| `src/tagmemorag/eval/runner.py` | new | build/load + search + aggregate |
| `src/tagmemorag/cli.py` | edit | add `eval run` subcommand |
| `src/tagmemorag/config.py` | edit | optional `EvalConfig` defaults if useful |
| `tests/fixtures/eval/coffee.jsonl` | new | first versioned suite |
| `tests/unit/test_eval_*.py` | new | loader/matching/metrics tests |
| `tests/e2e/test_eval_cli.py` | new | CLI pass/fail gate |
| `README.md` | edit | Quality Eval usage |

---

## 2. 数据契约

### 2.1 EvalSuite / EvalCase

```python
@dataclass(frozen=True)
class ExpectedResult:
    id: str | None = None
    source_file: str | None = None
    header: str | None = None
    anchor_key: str | None = None
    text_contains: tuple[str, ...] = ()
    weight: float = 1.0

@dataclass(frozen=True)
class EvalThresholds:
    min_precision_at_k: float | None = None
    min_recall_at_k: float | None = None
    min_mrr: float | None = None
    min_hit_at_k: float | None = None

@dataclass(frozen=True)
class EvalCase:
    id: str
    query: str
    relevant: tuple[ExpectedResult, ...]
    kb_name: str = "default"
    tags: tuple[str, ...] = ()
    notes: str = ""
    top_k_override: int | None = None
    thresholds: EvalThresholds = EvalThresholds()
```

JSONL example:

```json
{"id":"coffee-steam-weak","kb_name":"default","query":"蒸汽很小怎么办","relevant":[{"source_file":"coffee_machine.md","header":"蒸汽很小","text_contains":["清洗","蒸汽"]}],"tags":["coffee","troubleshooting"]}
```

Validation rules:

- `id` required, non-empty, unique in suite.
- `query` required, non-empty after strip.
- `relevant` required, at least one expected result.
- Every expected result must include at least one matcher field.
- `relevant[].id` is optional; reports should use it when present and otherwise generate `<case_id>#<index>`.
- `weight` must be positive. M3 stores it but binary metrics ignore it.

### 2.2 Matching Contract

`ExpectedResult` matches a `Result` when all specified fields match:

- `source_file`: exact stored `Result.source_file` match by default. A basename fallback is allowed only when it resolves to exactly one result file in the evaluated KB; ambiguous basename matches are suite/data errors, not successful matches.
- `header`: exact match after strip.
- `anchor_key`: exact match.
- `text_contains`: every substring must be present in `Result.text`.

Multiple expectations can match the same result, but metric calculation deduplicates by expectation index so recall cannot exceed 1.0.

### 2.3 Metric Contract

For one query:

```python
precision_at_k = relevant_hits_in_top_k / k
recall_at_k = matched_expected_count / expected_count
mrr = 1 / rank_of_first_relevant_result, or 0.0
hit_at_k = 1.0 if any relevant result appears in top_k else 0.0
```

Aggregate summary uses macro average across cases:

```python
summary.precision_at_k = mean(case.precision_at_k)
summary.recall_at_k = mean(case.recall_at_k)
summary.mrr = mean(case.mrr)
summary.hit_at_k = mean(case.hit_at_k)
```

Default `k=5`. If a case has `top_k_override`, runner uses that for retrieval and metrics for that case.

### 2.4 Report Contract

```json
{
  "suite": "tests/fixtures/eval/coffee.jsonl",
  "docs": "tests/fixtures",
  "kb_names": ["default"],
  "top_k": 5,
  "thresholds": {
    "min_recall_at_k": 0.8,
    "min_mrr": 0.75,
    "min_hit_at_k": 0.8
  },
  "summary": {
    "cases": 3,
    "passed": true,
    "precision_at_k": 0.86,
    "recall_at_k": 1.0,
    "mrr": 0.9,
    "hit_at_k": 1.0
  },
  "cases": [
    {
      "id": "coffee-steam-weak",
      "query": "蒸汽很小怎么办",
      "passed": true,
      "metrics": {"precision_at_k": 0.2, "recall_at_k": 1.0, "mrr": 1.0, "hit_at_k": 1.0},
      "expected": [...],
      "actual_top_k": [...]
    }
  ]
}
```

Report serialization should use stable key ordering where practical, and never include full config secrets.

---

## 3. CLI Design

Command:

```bash
uv run tagmemorag eval run \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --config config.yaml \
  --output .tmp/eval-report.json \
  --top-k 5 \
  --min-recall-at-k 0.8 \
  --min-mrr 0.75 \
  --min-hit-at-k 0.8
```

Options:

| Option | Required | Default | Notes |
|--------|----------|---------|-------|
| `--suite` | yes | - | JSONL path |
| `--docs` | conditional | - | Required unless `--reuse-built-kb` |
| `--config` | no | `config.yaml` | Existing loader |
| `--output` | no | stdout only | Write JSON report |
| `--top-k` | no | config/search default or 5 | CLI override wins |
| `--kb` | no | all kb in suite | Optional filter |
| `--reuse-built-kb` | no | false | Use existing storage instead of building from docs |
| `--eval-data-dir` | no | `.tmp/eval/<run_id>` | Temporary storage root when building from docs |
| `--min-precision-at-k` | no | unset | Optional gate threshold; reported by default but not gated by default |
| `--min-recall-at-k` | no | 0.8 | Gate threshold |
| `--min-mrr` | no | 0.75 | Gate threshold |
| `--min-hit-at-k` | no | 0.8 | Gate threshold |

Exit codes:

- `0`: suite loaded, eval ran, all thresholds passed.
- `1`: eval ran but thresholds failed.
- `2`: invalid arguments, invalid suite, build/load failure, or unexpected runtime error handled as user-facing failure.

---

## 4. Execution Flow

1. Load suite JSONL into `EvalCase` list.
2. Group cases by `kb_name`.
3. Resolve storage:
   - If `--reuse-built-kb`, use `cfg.storage.data_dir` as configured.
   - Else clone/derive `Settings` with `storage.data_dir = --eval-data-dir` (or a generated `.tmp/eval/<run_id>` path).
4. For each KB:
   - If `--reuse-built-kb`, call `load_kb(kb_name, cfg)`.
   - Else call `build_kb(docs, kb_name, cfg, embedder=embedder)`.
5. For each case:
   - Encode query using shared embedder.
   - Run `wave_search` with `top_k`.
   - Match results against expectations.
   - Compute case metrics and pass/fail.
6. Aggregate macro summary.
7. Apply suite thresholds, then apply any case-level thresholds as additional constraints.
8. Emit JSON report to output file and concise console summary.

Notes:

- Build once per KB, not once per query.
- Do not use query cache; eval measures underlying retrieval.
- Default docs-based eval must not read or write the normal `data/{kb_name}` tree. Because the existing `build_kb` reads anchors from `cfg.storage.data_dir`, runner must isolate `storage.data_dir` for eval builds instead of reusing the main config path.
- `--reuse-built-kb` is the explicit escape hatch for evaluating an already persisted KB and may read normal storage.

---

## 5. Error Handling

M3 should keep CLI errors human-readable and testable:

- Invalid JSON line: include file path and line number.
- Duplicate case id: include duplicated id.
- Missing docs path when not reusing KB: explain required option.
- Empty result set: report as case failure, not runner crash.
- Invalid thresholds: reject values outside `[0.0, 1.0]`.
- Ambiguous `source_file` basename expectation: include case id, expected id, basename, and candidate stored source files.
- Suite/data validation failures should use a dedicated eval exception (for example `EvalSuiteError`) so CLI can return exit code `2` without exposing tracebacks.

If the project later exposes these via API, map to existing structured error patterns. M3 CLI can use plain stderr plus exit code.

---

## 6. Testing Strategy

Unit:

- `test_eval_dataset.py`: valid JSONL, malformed JSON, duplicate id, empty relevant.
- `test_eval_matching.py`: exact header/source match, text_contains all required, non-match.
- `test_eval_metrics.py`: precision/recall/MRR/hit edge cases.
- `test_eval_runner.py`: default docs-based eval uses an isolated temp storage path and does not create or mutate the configured `data/{kb_name}`.

E2E:

- `test_eval_cli_passes_coffee_fixture`: deterministic suite passes default thresholds.
- `test_eval_cli_fails_threshold`: impossible threshold or altered expectation returns exit code 1 and writes report.

Regression:

- Existing `tests/e2e/test_coffee.py` can remain as smoke test or be folded into the eval suite after M3 is implemented.

---

## 7. Rollout / Rollback

Rollout:

1. Add eval package and unit tests.
2. Add CLI subcommand behind explicit invocation.
3. Add fixture suite and E2E gate.
4. Document local command.
5. If CI exists, add eval command after normal unit tests.

Rollback:

- If CLI integration causes issues, keep eval package and remove only the CLI subcommand temporarily.
- If default thresholds are flaky, lower thresholds in suite/config while preserving per-case report output.
- If fixture matching is too brittle, prefer `text_contains` plus `source_file` over exact `anchor_key`.
- If isolated storage behavior is difficult to integrate, pause before CLI gate rather than letting eval write to the main `data/` tree.

---

## 8. Out of Scope

- HTTP eval runner.
- Real model required in CI.
- LLM-as-judge.
- Weighted metrics using `weight`.
- Eval dashboard.
- Prometheus/OTel instrumentation.
