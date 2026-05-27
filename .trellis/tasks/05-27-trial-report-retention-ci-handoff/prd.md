# Trial Report Retention CI Handoff

## Goal

Document and verify retained trial report paths, browser readiness evidence, and CI handoff expectations.

## Requirements

- Document where trial operators should retain pilot/browser QA reports.
- Clarify the difference between local retained evidence and GitHub Actions CI gates.
- Keep browser QA and pilot browser stages opt-in in CI because they start a local browser/server.
- Link the handoff from the trial operator guide, quality gates, and README.
- Add a lightweight regression test so the documented handoff remains discoverable.

## Acceptance Criteria

- [ ] A trial operator can find the retained report command and expected report paths without reading terminal history.
- [ ] The docs state which checks GitHub Actions runs by default.
- [ ] The docs state which browser/pilot checks remain local opt-in.
- [ ] README and trial handoff link to the CI/report handoff.
- [ ] Focused docs/link test passes before commit and archive.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
