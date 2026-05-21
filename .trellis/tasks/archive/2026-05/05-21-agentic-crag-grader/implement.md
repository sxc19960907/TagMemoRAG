# C4 CRAG-lite Grader — Execution Plan

## 0. Operating Rules

- Keep reranker dispatcher zero-touch.
- Keep public surface untouched.
- No LLM calls.
- C4 should only add local deterministic grading and tests.

## 1. Implementation Steps

### Step 1 — Grader Module

- Add `src/tagmemorag/agentic/grader.py`.
- Implement `CragGradeThresholds` and `grade_rerank_result`.
- Export from `src/tagmemorag/agentic/__init__.py`.

Validation:

```bash
uv run pytest tests/unit/test_agentic_grader.py -q
```

### Step 2 — GradeTool Integration

- Update `src/tagmemorag/agentic/tools/grade.py`.
- Preserve dispatcher call signature.
- Return computed grade.

Validation:

```bash
uv run pytest tests/unit/test_agentic_tools_stub.py -q
```

### Step 3 — Driver Integration Test

- Add fake dispatcher/GradeTool harness showing low -> rewrite -> second
  retrieve.

Validation:

```bash
uv run pytest tests/unit/test_agentic_driver_loop.py -q
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

- [x] AC4.1-AC4.7 are all satisfied.
- [x] Full pytest passes.
- [x] C4 docs updated with validation results.
- [ ] C4 archived and committed.

## 4. Implementation Result (2026-05-21)

- Added `src/tagmemorag/agentic/grader.py` with `CragGradeThresholds` and
  deterministic `grade_rerank_result`.
- Updated `GradeTool` to return computed CRAG-lite signals from
  `RerankResult` while preserving dispatcher call shape.
- Fixed grade step recording so the persisted grade step stores the computed
  grade from the tool observation.
- Added tests for high/low/inconclusive/no-signal/empty-item derivation,
  GradeTool integration, and C3 low-signal loop integration.

Validation performed:

- `uv run pytest tests/unit/test_agentic_grader.py tests/unit/test_agentic_router.py tests/unit/test_agentic_driver_loop.py tests/unit/test_agentic_replay_verdict.py tests/unit/test_agentic_tools_registry.py tests/unit/test_agentic_tools_stub.py tests/unit/test_queryplan_plan.py tests/unit/test_queryplan_plan_log.py tests/unit/test_replay_runner.py tests/unit/test_reranker_dispatcher_cache_key_invariant.py tests/unit/test_eval_dataset.py -q` → 76 passed.
- `uv run pytest -q` → 1006 passed, 2 skipped.
- `git diff --check` → passed.
- `git diff --name-only HEAD -- src/tagmemorag/api.py src/tagmemorag/cli.py src/tagmemorag/config.py src/tagmemorag/production_provider_verify.py src/tagmemorag/reranker src/tagmemorag/answer/openai_compatible.py` → empty.
