# Reranking evaluation gate runner

## Goal

Implement a reusable offline gate runner for future reranking or
evidence-usefulness candidates.

The runner compares baseline and candidate release-readiness plus
general-web ranking-pressure reports, emits a bounded JSON/Markdown delta, and
exits non-zero when the candidate violates the ship gate defined in the
reranking evaluation batch plan.

## Context

- Release readiness is currently `passed`.
- General-web ranking pressure is non-blocking but tracked:
  `ranking_pressure_count=2`, `highest_pressure_rank_count=5`.
- A future ranking change must prove it does not regress release-readiness or
  worsen GitHub pressure cases.

## Requirements

- Add a pure Python module under `src/tagmemorag/` that compares baseline and
  candidate reports without running retrieval.
- Add a thin script under `scripts/` for CLI usage.
- Gate these conditions:
  - candidate release readiness must be `passed`,
  - general-web hit@k, recall@k, and MRR must not decrease,
  - ranking-pressure count and highest pressure rank count must not increase,
  - tracked GitHub pressure cases must not move to a later first matched rank.
- Output only bounded metrics and case ids from checked-in fixtures.
- Do not include raw queries, snippets, `actual_top_k`, vectors, secrets, or
  generated `.tmp` reports in committed artifacts.

## Acceptance Criteria

- [ ] Unit tests cover passing candidates and each major regression class.
- [ ] CLI returns `0` for a passing candidate and non-zero for a failing one.
- [ ] JSON and Markdown outputs are supported.
- [ ] Output is bounded and does not include raw query text or snippets.
- [ ] Existing focused release-readiness and ranking-pressure tests still pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
