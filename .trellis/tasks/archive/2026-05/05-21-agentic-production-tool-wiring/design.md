# Agentic Production Tool Wiring — Design

## Scope

Replace the remaining agentic stub-style retrieve/final wiring with production
retrieval and answer contracts while preserving the default-off agentic mode
surface.

This task should improve the internal agentic path only. Classic `/search`,
`/retrieve`, `/answer`, and default eval behavior must remain unchanged.

## Goals

- Agentic retrieve tool uses the same production retrieval response contract as
  `/retrieve` where practical.
- Agentic final tool generates from the latest retrieved context rather than a
  stale startup context.
- Agentic steps remain persisted through `PlanLog.plan_steps`.
- Budget and private-KB fallback behavior remains intact.
- Agentic eval slices remain named gates.

## Non-Goals

- Do not enable agentic mode by default.
- Do not replace the self-built agentic driver with LangChain/LangGraph.
- Do not add live provider gates or paid tests in this task.
- Do not change reranker dispatcher behavior.
- Do not tune prompt wording for quality; C5 owns prompt/context review.

## Proposed Shape

### Production Retrieve Tool

The current `RetrieveTool` already calls `execute_search` and
`build_retrieve_response`, but it owns its own query vector at construction
time. Production wiring should make each tool call encode the actual query it
receives, so rewrite iterations are meaningful.

Contracts:

- accepts `state`, `embedder`, `top_k`, `source_k`, trace/search/retrieve ids;
- on each call, reads `args["query"]` or fallback query;
- encodes that query with the provided embedder;
- delegates to existing retrieval/search runtime helpers;
- returns a normal retrieve payload inside `ToolObservation.payload`;
- does not write a second QueryPlan row. The enclosing agent run owns the
  single plan and appends step records.

### Production Final Tool

The current `FinalTool` delegates to an `AnswerGenerator`, but its context is
constructed before agentic retrieval finishes. Production wiring should build
the answer prompt from `ctx.history` / `ctx.plan` and the latest retrieve
observation at call time.

Contracts:

- if a latest retrieve observation exists, use its retrieve payload;
- build `AnswerPrompt` via existing `build_answer_prompt`;
- validate generated citations via `validate_generation_citations`;
- preserve answer warnings;
- if answer generation is disabled or evidence is insufficient, return the
  same error/refusal shape used by `/answer` where practical.

### Registry Assembly

Add a small builder/factory for production agentic tools, likely near
`agentic/tools/` or API wiring:

- register production `retrieve`, `grade`, `rewrite`, and `final`;
- use the existing `GradeTool` and `RewriteTool`;
- keep tests that use dummy registries unchanged.

### Runtime Surface

Agentic mode remains behind existing `Settings.agentic.mode` and request
override resolution. This task may add tests that call `run_agent` directly
with production tools first; API routing into agentic mode should be changed
only if there is already a clear existing switch point.

## Data Flow

```text
agentic run
  -> retrieve tool
     -> embed actual tool query
     -> execute_search + build_retrieve_response
     -> ToolObservation(payload=retrieve_payload)
  -> grade/rewrite loop
  -> final tool
     -> latest retrieve payload
     -> build_answer_prompt
     -> AnswerGenerator
     -> validate_generation_citations
     -> ToolObservation(payload={"answer": ...})
```

## Compatibility

- Classic mode remains byte-equivalent because the native `/retrieve` and
  `/answer` path is not changed.
- Private KBs still return classic fallback before tool calls.
- Budget exhaustion still returns classic fallback and records fallback steps.
- Rollback is reverting the production tool builder or disabling agentic mode.

## Validation Gates

- `agentic_simple_passthrough.jsonl`
- `agentic_multihop.jsonl`
- `agentic_low_recall_recovery.jsonl`
- `agentic_budget_breach.jsonl`
- replay verdict tests for persisted `plan_steps`
- existing answer API/prompt/generator tests
