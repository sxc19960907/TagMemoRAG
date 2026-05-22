# RAG Answer Quality Diagnostics

## Goal

Evaluate optional RAG diagnostics such as faithfulness/context relevance for answer quality, offline and provider-gated. Planning only until approved.

## Requirements

- Evaluate optional answer-quality diagnostics such as faithfulness,
  context relevance, answer relevance, citation support, and refusal quality.
- Keep diagnostics offline or non-blocking by default.
- Use fake/local judge tests unless a live provider gate is explicitly
  approved.

## Acceptance Criteria

- [x] Diagnostics report schema is bounded and safe.
- [x] Existing answer API and prompt behavior are unchanged by default.
- [x] At least one grounded and one ungrounded fixture are defined.
- [x] Provider/env requirements are explicit and skip safely when absent.
- [x] Rollback leaves existing ranking eval unchanged.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
