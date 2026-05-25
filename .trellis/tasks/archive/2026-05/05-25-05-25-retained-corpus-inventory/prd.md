# Retained corpus inventory

## Goal

Inventory retained eval suites, materialized corpora, retained reports, gate outputs, and coverage gaps.

## Requirements

- Inventory committed eval suites under `tests/fixtures/eval/`.
- Inventory available local materialized corpora under `.tmp/`, `data/`, and
  other existing non-committed runtime locations without committing their
  contents.
- Inventory retained reports under `.tmp/eval/` by file path, status, slice,
  and aggregate metrics where available.
- Identify coverage gaps for post-default-on monitoring, especially around
  mixed-domain, multiformat, realmanuals, and larger general-web slices.
- Produce a committed Markdown summary only; do not commit generated reports or
  source corpus bodies.
- Avoid unbounded source/user content, provider response bodies, secrets, full
  candidate lists, and fetched third-party document bodies.

## Acceptance Criteria

- [ ] `retained-corpus-inventory.md` exists under this task directory.
- [ ] The inventory lists current suites, corpora, retained reports, and gaps.
- [ ] The inventory recommends the next child task.
- [ ] Privacy scan over the committed inventory has no forbidden markers.
- [ ] Parent program log records the child result.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
