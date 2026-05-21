# C5 Budget and Fallback — Execution Plan

## 0. Operating Rules

- Keep C5 internal/default-off.
- Do not add public API/config fields.
- Do not touch reranker or answer provider source.
- Fallback payloads must be safe metadata only.

## 1. Implementation Steps

### Step 1 — Unified Fallback Helper

- Refactor `src/tagmemorag/agentic/driver.py` fallback helpers.
- Add `tool="fallback"` step writing for persisted budget fallbacks.
- Preserve existing error behavior when no fallback exists.

Validation:

```bash
uv run pytest tests/unit/test_agentic_driver_loop.py -q
```

### Step 2 — Private-KB Guard

- Add `plan.persist is False` guard before router/tool execution.
- Test no router/tool calls and no step writes.

Validation:

```bash
uv run pytest tests/unit/test_agentic_driver_loop.py -q
```

### Step 3 — Budget Coverage

- Cover max iterations, max tokens, and max tool calls.
- Verify fallback step payload is safe.

Validation:

```bash
uv run pytest tests/unit/test_agentic_driver_loop.py tests/unit/test_agentic_replay_verdict.py -q
```

### Step 4 — Regression Gate

Run:

```bash
uv run pytest tests/unit/test_agentic_grader.py \
  tests/unit/test_agentic_router.py \
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
  src/tagmemorag/production_provider_verify.py \
  src/tagmemorag/reranker \
  src/tagmemorag/answer/openai_compatible.py
```

Expected final command output: empty.

## 2. Known Environment Note

`ruff` and `mypy` are not installed in the current repo environment. If they
become available, run:

```bash
uv run ruff check src tests
uv run mypy src/tagmemorag/agentic src/tagmemorag/queryplan src/tagmemorag/replay
```

## 3. Exit Criteria

- [x] AC5.1-AC5.8 are all satisfied.
- [x] Full pytest passes.
- [x] C5 docs updated with validation results.
- [ ] C5 archived and committed.

## 4. Validation Results

- `uv run pytest tests/unit/test_agentic_driver_loop.py tests/unit/test_agentic_replay_verdict.py -q`
  passed: 21 passed in 0.11s.
- `uv run pytest tests/unit/test_agentic_grader.py tests/unit/test_agentic_router.py tests/unit/test_agentic_driver_loop.py tests/unit/test_agentic_replay_verdict.py tests/unit/test_agentic_tools_registry.py tests/unit/test_agentic_tools_stub.py tests/unit/test_queryplan_plan.py tests/unit/test_queryplan_plan_log.py tests/unit/test_replay_runner.py tests/unit/test_reranker_dispatcher_cache_key_invariant.py tests/unit/test_eval_dataset.py -q`
  passed: 81 passed in 0.43s.
- `uv run pytest -q` passed: 1011 passed, 2 skipped in 18.26s.
- `git diff --check` passed.
- `git diff --name-only HEAD -- src/tagmemorag/api.py src/tagmemorag/cli.py src/tagmemorag/config.py src/tagmemorag/production_provider_verify.py src/tagmemorag/reranker src/tagmemorag/answer/openai_compatible.py`
  returned no files.
