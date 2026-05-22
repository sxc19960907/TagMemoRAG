# QA quick starts and copy

## Goal

Improve the first-run and post-answer experience on `/qa` by adding suggested starter questions and a copy-answer action.

## Requirements

- Keep the existing `/qa/answer` API contract unchanged.
- Add a small set of suggested question buttons that populate and submit the composer.
- Suggestions must be generic product-manual troubleshooting prompts and must not expose KB selection.
- Add a copy-answer action that copies the current answer as readable plain text.
- The copy action should be disabled or hidden until an answer is available.
- Clipboard failure should degrade gracefully with user-visible status text.
- The page must continue to hide plan/build/debug identifiers and tuning controls.
- The layout must remain usable on desktop and mobile.

## Acceptance Criteria

- [x] `/qa` renders suggested question controls in the user page.
- [x] Clicking a suggestion asks that question through the existing `/qa/answer` flow.
- [x] Answer results expose a copy action that copies plain answer text without source-card UI text.
- [x] Static UI tests cover suggestions, copy action, and continued absence of KB/debug controls.
- [x] Focused UI/API tests and a browser smoke check pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
