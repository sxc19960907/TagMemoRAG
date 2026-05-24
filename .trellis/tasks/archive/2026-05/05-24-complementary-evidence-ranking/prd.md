# Improve complementary evidence ranking

## Goal

Improve same-document evidence ranking for real public-web multi-evidence questions so exact answer-bearing chunks rank ahead of broad overview/navigation-like chunks more often.

This continues the answer-quality mainline after the HTML import cleanup: the system can now recall the relevant evidence, but several real cases still place exact evidence at ranks 3-7.

## Requirements

- Use the existing real public-web benchmark as the driver, especially the low-MRR cases in `.tmp/eval/gap-general-web-after-main.json`.
- Diagnose whether the remaining weak cases are caused by lexical scoring, vector/hash scoring, fixture expectations, or context packing.
- If a narrow ranking improvement is justified, implement it in the local deterministic retrieval stack.
- Keep WAVE/geodesic rerank and external rerankers out of scope unless a future task supplies separate evaluation evidence.
- Preserve existing real-manual, mixed-domain, and multi-format benchmark behavior.
- Do not add new web sources in this task.

## Acceptance Criteria

- [x] A diagnostic note identifies the weak real cases, their current ranks, and the likely cause.
- [x] If code changes are made, focused unit tests cover the ranking behavior without relying on network access.
- [x] General-web retrieval and answer diagnostics pass after the change.
- [x] Multi-format, mixed-domain, and real-manual retrieval diagnostics remain green.
- [x] Trellis docs/journal are updated with the outcome and any follow-up boundary.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
