# Same-page ordering default-on implementation

## Goal

Flip same-page ordering to default-on after the parent readiness review,
without changing the ordering heuristic or broadening runtime behavior beyond
the existing guarded implementation.

## Requirements

- Change the default value of `search.same_page_ordering_enabled` from `false`
  to `true`.
- Keep `search.same_page_ordering_min_group_size=2`.
- Preserve explicit YAML and environment override behavior, including the
  ability to set `search.same_page_ordering_enabled=false` for rollback.
- Do not modify the same-page ordering heuristic in this task.
- Update tests and any expected config snapshots impacted by the default flip.
- Run focused config, retrieval, eval-runner, reranking gate batch, and release
  readiness checks.
- Do not commit generated `.tmp` reports or unbounded diagnostic content.

## Acceptance Criteria

- [x] Default `Settings().search.same_page_ordering_enabled` is `true`.
- [x] Explicit YAML/env false overrides remain effective.
- [x] Existing same-page safety tests still pass.
- [x] Candidate-aware gate batch and release readiness remain passing.
- [x] Parent program log records the default-on implementation result.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
