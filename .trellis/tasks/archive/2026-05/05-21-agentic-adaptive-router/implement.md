# C2 Adaptive Router — Execution Plan

## 0. Operating Rules

- Documentation first, implementation only after user approval.
- Keep C2 internal and default-off: no API, CLI, config, or eval surface
  wiring.
- Do not change C1 baselines unless a baseline bug is found and documented.
- Do not touch reranker or OpenAI-compatible answer source files.

## 1. Pre-Implementation Checklist

- [ ] User reviews this C2 PRD/design/implement packet.
- [ ] `task.py start .trellis/tasks/05-21-agentic-adaptive-router` is run
      only after approval.
- [ ] Confirm C1 commit is present in history:
      `git merge-base --is-ancestor 2340ca4c51c59e4935db1a0fc1bf49e176553bea HEAD`.
- [ ] Read backend specs listed in `implement.jsonl` and `check.jsonl`.

## 2. Implementation Steps

### Step 2.1 — Router Contract

- Add `src/tagmemorag/agentic/router.py`.
- Implement `RouteKind`, `RouteDecision`, `AdaptiveRouter`, and
  `RuleBasedAdaptiveRouter`.
- Export contracts from `src/tagmemorag/agentic/__init__.py`.

Validation:

```bash
uv run pytest tests/unit/test_agentic_router.py -q
```

### Step 2.2 — Rule Classification Tests

- Create `tests/unit/test_agentic_router.py`.
- Load `tests/fixtures/eval/agentic_simple_passthrough.jsonl` and assert
  every case routes `single_shot`.
- Add focused examples for `multi_hop` and `no_retrieval`.

Validation:

```bash
uv run pytest tests/unit/test_agentic_router.py tests/unit/test_eval_dataset.py -q
```

### Step 2.3 — Driver Preflight

- Extend `run_agent(..., router: AdaptiveRouter | None = None)`.
- Preserve exact C1 behavior when `router is None`.
- When router returns `single_shot` or `no_retrieval`, return the supplied
  `classic_fallback` exactly and skip retrieve/grade/final tool calls.
- Write a `tool="route"` step if `plan_log` is supplied.

Validation:

```bash
uv run pytest tests/unit/test_agentic_driver_loop.py -q
```

### Step 2.4 — Replay Route Step

- Add/extend replay unit coverage so route steps replay as deterministic rule
  steps.
- Avoid changing `plan_steps` schema.

Validation:

```bash
uv run pytest tests/unit/test_agentic_replay_verdict.py tests/unit/test_replay_runner.py -q
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

This repo environment currently does not install `ruff` or `mypy`; attempts
with `uv run ruff ...` and `uv run mypy ...` fail to spawn the executables.
If that changes, run:

```bash
uv run ruff check src tests
uv run mypy src/tagmemorag/agentic src/tagmemorag/queryplan src/tagmemorag/replay
```

## 4. Exit Criteria

- [x] AC2.1-AC2.8 are all satisfied.
- [x] C1 tests still pass.
- [x] Full pytest passes.
- [x] C2 task docs are updated with actual validation results.
- [ ] C2 is archived and committed.

## 5. Implementation Result (2026-05-21)

- Added `src/tagmemorag/agentic/router.py` with `RouteDecision`,
  `AdaptiveRouter`, and deterministic `RuleBasedAdaptiveRouter`.
- Exported router contracts from `src/tagmemorag/agentic/__init__.py`.
- Extended `run_agent` with optional router preflight while preserving C1
  behavior when `router is None`.
- Added route short-circuit behavior for `single_shot` and `no_retrieval`.
- Persisted route decisions as ordinary `tool="route"` `plan_steps` rows.
- Added unit coverage for router classification, driver short-circuit,
  persisted route steps, multi-hop continuation, and replay verdicts.

Validation performed:

- `uv run pytest tests/unit/test_agentic_router.py tests/unit/test_agentic_driver_loop.py tests/unit/test_agentic_replay_verdict.py tests/unit/test_agentic_tools_registry.py tests/unit/test_agentic_tools_stub.py tests/unit/test_queryplan_plan.py tests/unit/test_queryplan_plan_log.py tests/unit/test_replay_runner.py tests/unit/test_reranker_dispatcher_cache_key_invariant.py tests/unit/test_eval_dataset.py -q` → 63 passed.
- `uv run pytest -q` → 992 passed, 2 skipped.
- `git diff --check` → passed.
- `git diff --name-only HEAD -- src/tagmemorag/api.py src/tagmemorag/cli.py src/tagmemorag/config.py src/tagmemorag/reranker src/tagmemorag/answer/openai_compatible.py` → empty.
