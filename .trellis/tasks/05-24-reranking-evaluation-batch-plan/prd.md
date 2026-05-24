# Reranking evaluation batch plan

## Goal

Define the evaluation batch that must gate any future general-purpose
reranking or evidence-usefulness change.

The recent GitHub Hello World diagnosis found real but non-blocking ranking
pressure. The next safe step is not to tune runtime ranking directly; it is to
define a broader validation contract so a later reranking change can prove it
helps the GitHub pressure cases without regressing the passed release baseline.

## Context

- Release readiness is currently `passed`.
- General-web ranking pressure is visible but non-blocking:
  - `ranking_pressure_count=2`
  - `highest_pressure_rank_count=5`
- The two pressure cases are top-k hits from the GitHub Hello World document,
  with overview/workflow chunks outranking answer-specific evidence.
- Previous diagnostics rejected a broad lexical/ranking tweak from this thin
  signal.

## Requirements

- Produce a checked-in plan artifact for a future reranking/evidence-usefulness
  evaluation batch.
- The plan must cover all current release-readiness slices, not only
  general-web:
  - general-web retrieval,
  - mixed-domain retrieval,
  - multi-format retrieval,
  - real-manual retrieval,
  - context-quality normal and tight budget,
  - answer-quality diagnostics,
  - release-readiness aggregate status.
- Define the minimum ship gate for a future runtime ranking change.
- Define privacy constraints for reranking diagnostics.
- Keep this task documentation-only; do not change runtime retrieval behavior.

## Acceptance Criteria

- [ ] A plan artifact lists the required eval commands and pass/fail gates.
- [ ] The plan defines how GitHub ranking pressure should be measured.
- [ ] The plan states that release readiness must remain `passed`.
- [ ] The plan forbids committing raw `.tmp` reports, raw queries, snippets,
      vectors, provider secrets, or full candidate lists.
- [ ] The task is archived after the planning artifact is committed.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
