# User Facing KB Selection And Multi KB Clarity

## Goal

Make the user-facing QA page clearer about the active knowledge base and provide a browser-friendly way to switch between available knowledge bases.

## User Value

Users should know which knowledge base they are asking before they submit a question. When multiple KBs exist, switching should be visible and browser-native enough that users do not need to edit the URL by hand.

## Confirmed Facts

- The QA page currently reads `kb_name` from the URL and stores it in `state.kbName`.
- The QA page intentionally does not show a KB input today.
- `/kb` already returns available KBs for the current API token.
- Conversation history is keyed by KB, so changing KB should reload the page rather than silently reusing history.

## Requirements

- Show the active KB clearly in the QA left rail.
- Load available KBs from `/kb` and show them in a compact selector when available.
- Switching KB should navigate to `/qa?kb_name=<selected>` while preserving a prefilled `question` query parameter if present.
- Update RAG Readiness links and context copy to use the selected KB.
- Keep the current `/qa/answer` request behavior compatible with route clarification.
- Cover the markup/static asset and focused browser flow with tests.

## Acceptance Criteria

- [ ] `/qa?kb_name=ops` renders visible active-KB controls.
- [ ] `qa_page.js` fetches `/kb`, populates the selector, and falls back gracefully if the list cannot load.
- [ ] Browser QA readiness verifies the active KB label/selector on the first screen.
- [ ] Existing QA answer and feedback behavior remains intact.
- [ ] Focused unit/static/browser checks pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
