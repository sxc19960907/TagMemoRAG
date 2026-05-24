# Baseline batch self-check

## Goal

Run a bounded baseline self-check that confirms the current general-purpose RAG
quality gates are green before starting longer-horizon optimization work.

This child task belongs to `05-24-general-rag-stability-program`.

## Requirements

- Run release readiness with retained ranking-pressure input.
- Run the reranking evaluation gate against the current baseline as a
  self-comparison.
- Run focused unit tests for release readiness, ranking pressure, and reranking
  gate.
- Record bounded results in this task and update the parent program log.
- Do not modify runtime behavior.
- Do not commit generated `.tmp` reports.

## Acceptance Criteria

- [ ] Release readiness self-check is `passed`.
- [ ] Reranking evaluation gate self-check is `passed`.
- [ ] Focused tests pass.
- [ ] Parent `program-log.md` records the result and recommended next child.
- [ ] Generated reports remain uncommitted.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
