# Final Trial Readiness Review

## Goal

Run final local trial readiness checks and capture GitHub/CI follow-up status.

## Requirements

- Run a final local quality slice that covers the completed trial operations work.
- Retain or refresh browser QA / pilot evidence when feasible.
- Capture the current GitHub/CI follow-up status without pushing unless explicitly requested.
- Mark the parent task complete only if the local gates pass and completed children are archived.

## Acceptance Criteria

- [ ] Focused unit/docs/browser-readiness gates pass.
- [ ] Trial operator docs point to retained report and CI handoff.
- [ ] Parent task checklist is complete.
- [ ] Remaining follow-up is limited to GitHub push/CI verification.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
