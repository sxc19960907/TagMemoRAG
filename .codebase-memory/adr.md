# ADR: Self-built Agentic Loop Driver

Date: 2026-05-21
Status: accepted

## Context

Agentic RAG mode needs replayable multi-step trajectories on top of the existing QueryPlan, PlanLog, BudgetGuard, reranker dispatcher, and answer provider contracts. Framework checkpointers from LangGraph/LlamaIndex would create a second state source and make replay/eval harder to reason about.

## Decision

Build a lightweight in-repo agentic loop under `src/tagmemorag/agentic/`, keeping PlanLog as the source of truth. Tool schemas remain OpenAI/MCP-compatible so future framework adapters can wrap the registry without changing the persistence model.

## Consequences

- Classic mode remains default-off and byte-equivalent by default.
- Agentic runs append ordered `plan_steps` records for replay.
- Budget exhaustion and private KBs degrade through a deterministic fallback path.
- Future LangChain/LangGraph integration should be adapter-level, not a replacement for PlanLog ownership unless a new parent task explicitly redesigns replay storage.