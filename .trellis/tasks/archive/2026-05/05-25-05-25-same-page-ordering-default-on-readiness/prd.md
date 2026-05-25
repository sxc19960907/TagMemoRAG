# Same-page ordering default-on readiness review

## Goal

Produce a parent-level readiness review for the same-page ordering runtime
flag after the ten completed stability-program children, and decide whether
the flag should be proposed for default-on rollout or remain opt-in.

## Requirements

- Review the committed parent program log and release candidate summary.
- Record a bounded operator-facing readiness decision under this task.
- Include the exact current runtime keys:
  `search.same_page_ordering_enabled` and
  `search.same_page_ordering_min_group_size`.
- Include evidence coverage, gate status, residual risks, rollback path, and
  next-step recommendation.
- Do not change runtime defaults in this task.
- Do not include raw queries, raw snippets, `actual_top_k`, vectors, provider
  responses, secrets, or generated `.tmp` report payloads.

## Acceptance Criteria

- [ ] A readiness review Markdown artifact exists under this task directory.
- [ ] The review gives a clear `propose-default-on`, `hold-opt-in`, or
      `rollback` decision.
- [ ] The review cites bounded metrics and status only, not raw diagnostic
      payloads.
- [ ] Focused stability tests still pass or no-code rationale is recorded.
- [ ] Parent program log records the decision and next stage.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
