# Same-page ordering release candidate summary

## Goal

Create an operator-facing same-page ordering release candidate summary that records default-off status, cross-domain enabled metrics, gate results, risks, and rollback notes.

## Requirements

- Produce a committed Markdown release candidate summary for the same-page
  ordering flag.
- Include default-off status and the exact config keys:
  `search.same_page_ordering_enabled` and
  `search.same_page_ordering_min_group_size`.
- Include bounded cross-domain enabled metrics from the retained validation
  runs: general-web, mixed-domain, multiformat, and realmanuals.
- Include reranking gate batch status, release-readiness status, and failed
  checks.
- Include risk notes and rollback instructions.
- Do not include raw queries, raw snippets, `actual_top_k`, vectors, provider
  responses, secrets, or full source-file lists.
- Do not change runtime defaults.

## Acceptance Criteria

- [ ] `release-candidate-summary.md` exists under the task directory.
- [ ] The summary is operator-facing and bounded to statuses, metrics, paths,
  decisions, risk notes, and rollback notes.
- [ ] Focused adjacent tests still pass or a no-code justification is recorded.
- [ ] The committed summary is privacy-scanned for forbidden raw markers.
- [ ] Parent program log records the child result and next decision point.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
