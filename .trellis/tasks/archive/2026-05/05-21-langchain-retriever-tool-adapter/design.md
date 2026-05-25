# LangChain Retriever and Tool Adapter — Design

## Scope

Expose TagMemoRAG retrieval and agent tools through LangChain-compatible
adapter objects while preserving TagMemoRAG as the runtime owner of retrieval,
QueryPlan, PlanLog, replay, and agentic orchestration.

This task is an integration facade, not a runtime migration to LangChain agents
or LangGraph.

## Goals

- Provide a LangChain retriever adapter that delegates to TagMemoRAG retrieval.
- Provide tool wrappers for `AgentToolRegistry` entries when LangChain is
  installed.
- Keep `langchain` as an optional extra; base install must continue to import.
- Ensure adapter-backed retrieval still creates QueryPlan/PlanLog records.
- Preserve classic retrieval output and existing public API behavior by
  default.

## Non-Goals

- Do not replace `execute_search`, `/retrieve`, QueryPlan/PlanLog, replay, or
  `agentic/` orchestration.
- Do not introduce a default runtime dependency on LangChain.
- Do not add a LangChain vector store around NPZ/Qdrant in this task.
- Do not enable adapter use in normal `/retrieve` or `/answer` paths.

## Proposed Shape

### Optional Dependency Boundary

Reuse the existing `langchain` extra added by the loader/splitter work.
`src/tagmemorag/langchain_adapter/` remains importable without LangChain. Any
LangChain-specific imports must be lazy and raise the existing
`LangChainAdapterUnavailable` style error when the extra is missing.

### Retriever Adapter

Add a small module, likely `src/tagmemorag/langchain_adapter/retriever.py`.
The adapter should accept already-owned TagMemoRAG dependencies rather than
construct global state:

- `state: GraphState`
- `settings: Settings`
- `embedder`
- search parameters such as `top_k`, `source_k`, `steps`, `decay`, and
  `aggregate`

The adapter exposes a LangChain `BaseRetriever`-compatible object when
LangChain is installed. Calling it should:

1. encode the query with the provided embedder;
2. delegate to existing retrieval/search runtime code that already wires
   QueryPlan/PlanLog;
3. convert returned evidence/results into LangChain `Document` objects;
4. carry low-sensitive metadata such as `source_file`, `header`, `score`,
   `chunk_id`, `citation_id`, `plan_id`, and `build_id`.

If the lowest-risk existing callable is `/retrieve` internals, use that. If
only `execute_search` is practical for the first pass, add the missing PlanLog
wireup at the adapter boundary rather than bypassing the acceptance criteria.

### Agent Tool Wrappers

Add a module, likely `src/tagmemorag/langchain_adapter/tools.py`, that converts
`AgentToolRegistry` definitions into LangChain tools when LangChain is
available.

Contracts:

- wrapper names and descriptions mirror registry tool definitions;
- input payloads remain dict-shaped and JSON-serializable;
- execution delegates to registry tools;
- wrapper output remains bounded string or dict output accepted by LangChain;
- no change to the registry itself unless needed for a stable introspection
  method.

### Tests

Use fake/local dependencies where possible. Tests should verify:

- base package import does not require LangChain;
- adapter unavailable error is clear when LangChain is missing, or wrappers
  can be exercised with installed extra;
- adapter-backed calls create QueryPlan rows when persistence is enabled;
- private KB or disabled persistence behavior remains consistent with
  existing QueryPlan rules;
- agentic tool registry tests stay green;
- classic retrieval/eval tests stay green.

## Data Flow

```text
LangChain caller
  -> TagMemoRAG retriever adapter
  -> embedder.encode_query
  -> TagMemoRAG retrieve/search runtime + QueryPlan/PlanLog
  -> retrieval results/evidence/context
  -> LangChain Document list
```

Tool wrappers:

```text
LangChain tool call
  -> adapter wrapper
  -> AgentToolRegistry tool
  -> bounded tool result
```

## Compatibility

- Normal `/retrieve`, `/search`, `/answer`, and eval commands are unchanged.
- Adapter modules are delete-only rollback.
- No base dependency or import-time LangChain requirement.
- Future C4 agentic production wiring may reuse the wrappers but does not
  depend on them.

## Rollback

Rollback by deleting retriever/tool adapter modules and tests. Existing native
retrieval, agentic registry, QueryPlan, and replay paths remain unchanged.
