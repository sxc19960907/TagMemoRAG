# Feedback To Eval Loop Smoothing

## Goal

Smooth the browser path from Q&A feedback to reviewable/promotable eval cases so quality issues become repeatable checks with less operator friction.

## User Value

When a user marks an answer as not helpful, the operator should be able to jump directly to the captured feedback record, review the cited evidence, add expected evidence, and turn the case into an eval draft without hunting through the feedback table.

## Confirmed Facts

- Q&A feedback already posts to `/search/feedback`.
- Retrieval Quality already supports review, expected evidence editing, promotion preview, export, and launching the generated eval draft in the browser.
- Browser tests already cover the not-helpful Q&A feedback path and the promotion/export path.
- The missing piece is a direct browser handoff from the saved Q&A feedback notification to the corresponding Retrieval Quality record.

## Requirements

- After Q&A feedback is saved, show a direct link to Retrieval Quality for that feedback record.
- The link must include `kb_name` and `feedback_id`.
- Retrieval Quality must read `feedback_id` from the URL and auto-select the matching row after feedback loads.
- The flow must degrade gracefully if the feedback record is not in the loaded page.
- Keep existing promotion API contracts unchanged.
- Update focused unit/static and browser coverage.

## Acceptance Criteria

- [ ] Q&A feedback saved state includes a visible review link.
- [ ] Retrieval Quality auto-selects a feedback record from `feedback_id`.
- [ ] Browser QA readiness still covers feedback capture, review, expected evidence, preview, export, and eval run launch.
- [ ] Existing feedback promotion behavior remains intact.
- [ ] Focused validation commands pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
