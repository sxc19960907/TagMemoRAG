# Same-page ordering cross-domain guard

## Goal

Expand same-page ordering enabled validation across retained multiformat and realmanuals slices without changing default runtime behavior.

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
# Same-Page Ordering Cross-Domain Guard

## Problem

The same-page ordering flag is now validated on general-web and mixed-domain,
and the batch gate can derive candidate pressure from eval reports. Before any
default-on discussion, the enabled flag needs broader guard evidence on retained
non-GitHub slices, especially multiformat and realmanuals where document shape
and page/header grouping differ from web docs.

## Goals

- Run `search.same_page_ordering_enabled=true` against locally retained
  multiformat and realmanuals eval slices when their docs are present.
- Compare enabled reports against the retained/default-off baseline reports for
  hit@k, recall@k, MRR, and failed case ids.
- Keep the feature default-off regardless of this child result.
- Produce bounded task notes and parent-program log entries without committing
  generated `.tmp` reports.

## Non-Goals

- Do not change same-page ordering heuristics unless the guard exposes a clear
  regression that must be fixed before continuing.
- Do not fetch new remote documents.
- Do not add live-provider dependencies.
- Do not promote the same-page flag to default-on in this child.

## Acceptance Criteria

- At least one retained non-general-web slice is evaluated with
  `same_page_ordering_enabled=true`; run both multiformat and realmanuals when
  local docs are available.
- Enabled-slice metrics and baseline comparisons are recorded in task docs and
  the parent program log.
- Any regression is classified explicitly as `ship`, `hold`, `pivot`, or
  `rollback`.
- Focused adjacent tests for same-page ordering and eval wiring pass.
- Generated reports are privacy-scanned for forbidden diagnostic markers before
  recording results.
