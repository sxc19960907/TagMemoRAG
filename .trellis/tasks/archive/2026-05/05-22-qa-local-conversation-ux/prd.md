# QA local conversation UX

## Goal

Make `/qa` feel more conversational by showing a lightweight local conversation history beside the answer workspace.

## Requirements

- Keep the backend `/qa/answer` request/response contract unchanged.
- Store conversation history only in the current browser page session; do not persist user questions or answers.
- Show recent turns in the left rail with question text and answer/refusal/error status.
- Let users click a history item to restore that turn's answer, sources, follow-ups, and feedback state.
- Mark the active turn while an answer is pending and after it completes.
- Keep quick-start suggestions and the no-KB-selector user experience intact.
- Keep debug identifiers such as plan ids and build ids out of the user page.

## Acceptance Criteria

- [x] `/qa` renders a conversation history container in the user shell.
- [x] `qa_page.js` records pending, answered, refusal, and error turns in local state.
- [x] Clicking a history item restores the selected turn without another network request.
- [x] Existing quick-start, copy, feedback, follow-up, citation, and source behavior still work.
- [x] Focused UI/API tests pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
