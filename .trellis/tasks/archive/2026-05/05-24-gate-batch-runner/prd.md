# Gate batch runner

## Goal

Add a repeatable offline batch runner that executes the current release
readiness and reranking gate self-check as one command.

This child task belongs to `05-24-general-rag-stability-program`. It automates
the manual baseline self-check proven by the previous child task.

## Requirements

- Add a pure Python module and script for the batch self-check.
- Reuse existing release readiness and reranking gate modules instead of
  duplicating gate logic.
- Accept report path overrides for required inputs and an output directory.
- Write bounded JSON reports:
  - release readiness,
  - reranking gate,
  - batch summary.
- Exit non-zero if readiness or gate fails.
- Preserve privacy: no raw query text, snippets, `actual_top_k`, full candidate
  lists, vectors, provider responses, or secrets in the batch summary.
- Do not change retrieval/ranking runtime behavior.

## Acceptance Criteria

- [ ] Unit tests cover passing and failing batch outcomes.
- [ ] CLI self-check passes on retained baseline reports.
- [ ] Output summary is bounded and references generated reports by path only.
- [ ] Focused readiness/gate tests remain green.
- [ ] Parent program log records the result and next recommendation.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
