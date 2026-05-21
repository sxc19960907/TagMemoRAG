# LangChain Retriever and Tool Adapter

## Goal

Expose TagMemoRAG retrieval and agent tools through LangChain-compatible adapters without replacing QueryPlan/PlanLog. Planning only until approved.

## Requirements

- Expose TagMemoRAG retrieval through a LangChain-compatible retriever
  adapter without replacing QueryPlan/PlanLog.
- Expose AgentToolRegistry tools through compatible tool wrappers when useful.
- Keep classic retrieval output byte-stable by default.

## Acceptance Criteria

- [ ] QueryPlan rows are still written by adapter-backed calls.
- [ ] Replay still works for adapter-backed calls.
- [ ] Agentic tool registry tests stay green.
- [ ] No default runtime dependency on LangChain unless the child explicitly
      approves an extra.
- [ ] Rollback is deleting the adapter package.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
