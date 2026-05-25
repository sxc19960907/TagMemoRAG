# C3 Iterative Multi-hop — Execution Plan

## 0. Operating Rules

- Keep the task internal/default-off.
- Implement loop mechanics only; do not implement CRAG score thresholds.
- Do not change public API/CLI/config.
- Do not touch reranker or OpenAI-compatible answer source.

## 1. Pre-Implementation Checklist

- [ ] User has approved C3 PRD/design/implement.
- [ ] Start task with:
      `python3 .trellis/scripts/task.py start .trellis/tasks/05-21-agentic-iterative-multihop`
- [ ] Confirm C2 commit is present in history.
- [ ] Read manifests in `implement.jsonl` and `check.jsonl`.

## 2. Implementation Steps

### Step 2.1 — Rewrite Tool Contract

- Update `src/tagmemorag/agentic/tools/rewrite.py`.
- Add deterministic append-term rewrite behavior.
- Add/adjust tests in `tests/unit/test_agentic_tools_stub.py` or a new
  focused test file.

Validation:

```bash
uv run pytest tests/unit/test_agentic_tools_stub.py -q
```

### Step 2.2 — Driver Iteration

- Replace single `retrieve -> grade -> final` block in `run_agent` with a
  bounded rule loop.
- On `low`, call `rewrite`, update `current_query`, then retrieve again.
- Preserve C1 `no_signal` final path and C2 route short-circuit path.

Validation:

```bash
uv run pytest tests/unit/test_agentic_driver_loop.py -q
```

### Step 2.3 — Budget Fallback

- Ensure budget exhaustion before rewrite/second retrieve returns
  `classic_fallback` when supplied.
- Add a focused test for exhaustion in the low-signal loop.

Validation:

```bash
uv run pytest tests/unit/test_agentic_driver_loop.py -q
```

### Step 2.4 — Replay Coverage

- Add rewrite-containing sequence coverage to
  `tests/unit/test_agentic_replay_verdict.py`.

Validation:

```bash
uv run pytest tests/unit/test_agentic_replay_verdict.py -q
```

### Step 2.5 — Regression Gate

Run:

```bash
uv run pytest tests/unit/test_agentic_router.py \
  tests/unit/test_agentic_driver_loop.py \
  tests/unit/test_agentic_replay_verdict.py \
  tests/unit/test_agentic_tools_registry.py \
  tests/unit/test_agentic_tools_stub.py \
  tests/unit/test_queryplan_plan.py \
  tests/unit/test_queryplan_plan_log.py \
  tests/unit/test_replay_runner.py \
  tests/unit/test_reranker_dispatcher_cache_key_invariant.py \
  tests/unit/test_eval_dataset.py -q

uv run pytest -q

git diff --check
git diff --name-only HEAD -- \
  src/tagmemorag/api.py \
  src/tagmemorag/cli.py \
  src/tagmemorag/config.py \
  src/tagmemorag/reranker \
  src/tagmemorag/answer/openai_compatible.py
```

Expected final command output: empty.

## 3. Known Environment Note

`ruff` and `mypy` are not installed in the current repo environment. If they
become available, run:

```bash
uv run ruff check src tests
uv run mypy src/tagmemorag/agentic src/tagmemorag/queryplan src/tagmemorag/replay
```

## 4. Exit Criteria

- [x] AC3.1-AC3.8 are all satisfied.
- [x] Full pytest passes.
- [x] C3 docs updated with validation results.
- [ ] C3 archived and committed.

## 5. Implementation Result (2026-05-21)

- Upgraded `RewriteTool` to deterministic append-term rewriting with safe
  original-query hash metadata.
- Extended `run_agent` to loop on `GradeOutcome(signal="low")` through
  `rewrite -> retrieve -> grade`.
- Preserved C1 `no_signal` finalization and C2 route short-circuit behavior.
- Added graceful fallback when agentic budget is exhausted mid-loop and
  `classic_fallback` is available.
- Added tests for low-signal iteration, rewrite-to-second-retrieve data flow,
  route + multi-hop composition, budget fallback, rewrite tool payloads, and
  replay of rewrite sequences.

Validation performed:

- `uv run pytest tests/unit/test_agentic_router.py tests/unit/test_agentic_driver_loop.py tests/unit/test_agentic_replay_verdict.py tests/unit/test_agentic_tools_registry.py tests/unit/test_agentic_tools_stub.py tests/unit/test_queryplan_plan.py tests/unit/test_queryplan_plan_log.py tests/unit/test_replay_runner.py tests/unit/test_reranker_dispatcher_cache_key_invariant.py tests/unit/test_eval_dataset.py -q` → 68 passed.
- `uv run pytest -q` → 998 passed, 2 skipped.
- `git diff --check` → passed.
- `git diff --name-only HEAD -- src/tagmemorag/api.py src/tagmemorag/cli.py src/tagmemorag/config.py src/tagmemorag/reranker src/tagmemorag/answer/openai_compatible.py` → empty.
