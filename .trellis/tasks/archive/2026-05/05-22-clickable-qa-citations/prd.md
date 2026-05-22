# Clickable QA citations

## Goal

Make the user-facing `/qa` answer easier to read and verify by turning inline citation markers into clickable controls that focus the matching source card.

## Requirements

- Preserve the existing `/qa/answer` API contract; this is a front-end rendering change only.
- Render answer text safely without allowing HTML injection from generated text.
- Convert citation markers such as `[cit_001]` in answer text into clickable citation chips.
- Clicking a citation chip should scroll the corresponding right-side source card into view and highlight it.
- Source cards should expose stable citation-based ids/data attributes for linking.
- The user page must continue to hide debug identifiers and KB selection controls.
- The layout must remain usable on desktop and mobile.

## Acceptance Criteria

- [x] `qa_page.js` renders inline citation chips from answer text.
- [x] Citation chips focus/highlight the corresponding source card.
- [x] Source cards carry citation ids without exposing plan/build/debug identifiers.
- [x] Static asset tests cover the new rendering/linking behavior.
- [x] Focused UI/API tests and a browser smoke check pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
