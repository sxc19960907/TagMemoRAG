# LangChain Retriever and Tool Adapter — Implementation Plan

## Operating Rules

- Adapter only: do not route native runtime through LangChain.
- Preserve QueryPlan/PlanLog as source of truth.
- Keep LangChain optional and lazy-imported.
- Keep tests deterministic and network-free.

## Steps

### Step 1 — Inspect Native Retrieval and Agent Tool Contracts

- Read existing `/retrieve` implementation and lower-level retrieval helpers.
- Identify the smallest native callable that returns evidence/context while
  preserving QueryPlan/PlanLog writes.
- Read `AgentToolRegistry` and tool tests to identify stable introspection and
  execution APIs.
- Check existing `langchain_adapter` import/unavailable patterns.

### Step 2 — Add Retriever Adapter

- Add a lazy LangChain adapter module.
- Define a factory/class that accepts explicit TagMemoRAG state/settings/embedder
  dependencies.
- Delegate query execution to native retrieval/search code.
- Convert results to LangChain `Document` objects with bounded metadata.
- Add tests for successful conversion and no base import dependency.

### Step 3 — Preserve QueryPlan/PlanLog

- Add or reuse a plan logging path for adapter-backed calls.
- Test that adapter-backed calls write QueryPlan rows when persistence is
  enabled.
- Test that replay can read the produced plan rows or that existing replay
  loader remains compatible with them.

### Step 4 — Add Agent Tool Wrappers

- Add wrappers around registry tools if LangChain's tool API is available.
- Keep registry behavior unchanged.
- Add tests that wrapper metadata mirrors registry definitions and execution
  delegates correctly.

### Step 5 — Validate

- Run focused adapter, queryplan, replay, and agentic tool tests.
- Run classic eval/retrieval tests to prove default output remains unchanged.
- Run full unit/e2e suite if focused checks pass.

## Validation Commands

```bash
uv run pytest tests/unit/test_langchain_adapter.py tests/unit/test_queryplan_plan_log.py tests/unit/test_replay_loader.py tests/unit/test_agentic_tools_registry.py
uv run pytest tests/unit/test_retrieval.py tests/unit/test_eval_runner.py tests/e2e/test_eval_cli.py
uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py
git diff --check
```

## Exit Criteria

- [x] QueryPlan rows are still written by adapter-backed calls.
- [x] Replay still works for adapter-backed calls.
- [x] Agentic tool registry tests stay green.
- [x] No default runtime dependency on LangChain unless the child explicitly
      approves an extra.
- [x] Rollback is deleting the adapter package.
