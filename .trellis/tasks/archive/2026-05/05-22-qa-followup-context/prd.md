# QA follow-up context

## Goal

Let `/qa` answer short follow-up questions using the current page conversation context while keeping the experience non-persistent and user-facing.

## Requirements

- Extend `POST /qa/answer` with an optional, bounded page-session context payload.
- Use the context only to improve routing and retrieval for the current request; do not persist raw context.
- Preserve the original user question in the response for display and history.
- Keep the browser from sending `kb_name`, `top_k`, `source_k`, plan ids, build ids, or debug controls.
- Keep admin/debug endpoints unchanged.
- Bound context size and trim text so accidental long answers do not become large request bodies.
- Keep existing single-turn `/qa` behavior compatible when no context is sent.

## Acceptance Criteria

- [x] Frontend sends recent page-session context with follow-up and typed questions.
- [x] Backend combines context with the current question for `/qa/answer` routing and retrieval.
- [x] Multi-KB routing can use prior context to route an ambiguous follow-up.
- [x] Response includes the original user question and does not surface debug identifiers in the user page.
- [x] Focused UI/API tests pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
