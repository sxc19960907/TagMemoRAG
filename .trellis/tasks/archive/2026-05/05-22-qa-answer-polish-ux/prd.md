# QA answer polish UX

## Goal

Improve the `/qa` user experience after the three-pane shell by making the answer flow feel clearer, more interactive, and less like a raw retrieval/debug surface.

## Requirements

- Keep the `/qa/answer` API contract unchanged; this task is a front-end polish pass over the existing response.
- Do not reintroduce a user-facing knowledge-base selector or debug identifiers on the user Q&A page.
- Show a richer empty state that nudges users toward symptom/task questions without requiring them to know which manual is loaded.
- Show staged loading copy while an answer request is in flight.
- After a grounded answer, show local answer feedback controls for "helpful" and "not helpful" without claiming durable persistence.
- After a grounded answer, show follow-up question suggestions that reuse the existing ask flow.
- Render source cards with citation, source, and section context up front; show a concise snippet by default and allow expanding to the full text.
- Keep the UI compact and consistent with the existing three-pane layout.

## Acceptance Criteria

- [x] `/qa` renders answer feedback, follow-up, staged loading, and source expansion containers.
- [x] `/static/manual-library/qa_page.js` includes handlers for staged loading, feedback, follow-up questions, and source expansion.
- [x] Focused unit tests for the manual-library UI pass.
- [x] Browser smoke verifies the page can ask from a suggestion and the new controls appear after the answer.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
