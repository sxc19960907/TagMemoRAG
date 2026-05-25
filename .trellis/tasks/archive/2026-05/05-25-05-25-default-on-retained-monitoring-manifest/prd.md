# Default-on retained monitoring manifest

## Goal

Create a manifest-driven bounded summary for post-default-on retained RAG monitoring.

## Requirements

- Add a committed manifest describing the current post-default-on retained
  monitoring slices and report paths.
- Add package code that reads the manifest and existing bounded eval/gate
  reports to produce a bounded monitoring summary.
- Add a CLI wrapper under `scripts/` for local use.
- Include JSON and Markdown output support.
- Include focused tests for passing summaries, missing reports, threshold
  failures, CLI behavior, and privacy omissions.
- Do not rerun live provider calls or fetch corpora in this task.
- Do not commit generated `.tmp` reports or unbounded source/user content.

## Acceptance Criteria

- [ ] A default-on monitoring manifest is committed.
- [ ] A bounded monitoring summary can be generated from retained local reports.
- [ ] Missing or regressed slice reports are visible as failed checks.
- [ ] Focused tests pass.
- [ ] Parent program log records the child result and next recommendation.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
