# Agentic Production Tool Wiring — Implementation Plan

## Operating Rules

- Keep agentic mode default-off.
- Do not change classic `/retrieve` or `/answer` behavior.
- Reuse production retrieval/answer helpers; do not create a second RAG stack.
- Keep tests offline and deterministic.

## Steps

### Step 1 — Inspect Existing Agentic Runtime

- Locate current API/eval/replay switch points for `mode=agentic`.
- Locate tool registry assembly and current retrieve/final tool construction.
- Confirm budget/private-KB fallback tests before editing.

### Step 2 — Productionize Retrieve Tool

- Update `RetrieveTool` to encode the actual query for each call or add a new
  production retrieve tool with that behavior.
- Keep the retrieve payload schema compatible with `build_retrieve_response`.
- Add a regression test proving rewrite query text changes retrieval input.

### Step 3 — Productionize Final Tool

- Add a dynamic final tool that builds answer context from latest retrieve
  observation.
- Reuse `build_answer_prompt`, `validate_generation_citations`, and
  `AnswerGenerator`.
- Add tests for citation validation and disabled/insufficient-evidence behavior
  if that behavior is implemented here.

### Step 4 — Registry Builder / Runtime Wiring

- Add or update production registry assembly so agentic mode can use production
  retrieve/final tools.
- Preserve existing stub tests and dummy-registry tests.
- Add tests that `run_agent` with production tools appends retrieve/grade/final
  steps and returns an answer derived from retrieved context.

### Step 5 — Validate Gates

- Run agentic unit tests.
- Run eval slices in classic and agentic forced modes where existing eval
  supports it.
- Run full unit/e2e suite.

## Validation Commands

```bash
uv run pytest tests/unit/test_agentic_driver_loop.py tests/unit/test_agentic_tools_stub.py tests/unit/test_agentic_router.py tests/unit/test_agentic_replay_verdict.py
uv run pytest tests/unit/test_answer_api.py tests/unit/test_answer_prompt.py tests/unit/test_answer_generator.py
uv run pytest tests/unit/test_eval_runner.py tests/e2e/test_eval_cli.py
uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py
git diff --check
```

Optional eval commands, if runtime wiring reaches eval in this task:

```bash
uv run python -m tagmemorag eval run \
  --config examples/config/local-hashing-npz.yaml \
  --suite tests/fixtures/eval/agentic_simple_passthrough.jsonl \
  --docs tests/fixtures \
  --eval-data-dir .tmp/eval-agentic-simple \
  --force-mode agentic \
  --min-recall-at-k 0.0 \
  --min-mrr 0.0 \
  --min-hit-at-k 0.0
```

## Exit Criteria

- [x] `agentic_simple_passthrough.jsonl` remains classic-equivalent where
      expected.
- [x] `agentic_multihop.jsonl`, `agentic_low_recall_recovery.jsonl`, and
      `agentic_budget_breach.jsonl` are named gates.
- [x] Replay verdict remains `match` or documented tolerated drift.
- [x] Agentic mode remains default-off.
- [x] Rollback is disabling agentic mode or reverting tool wiring.
