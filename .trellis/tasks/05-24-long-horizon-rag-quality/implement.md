# Implementation Plan

## Phase 1: Baseline Matrix

1. [x] Run current real retrieval diagnostics:
   - general web
   - multi-format
   - mixed-domain
   - real manuals
2. [x] Run current answer-quality diagnostics:
   - general web answer
   - multi-format answer
   - product-manual QA answer-quality
3. [x] Write `quality-program-notes.md` with metric summaries and weakest cases.

## Phase 2: Coverage Review

4. [x] Identify current coverage gaps across domain, format, language, and query type.
5. [x] Add or improve one real-data fixture/diagnostic if the gap is actionable in this phase; otherwise document why existing coverage is enough.

## Phase 3: Quality Batch

6. [x] Choose one concrete weakness from the baseline matrix.
7. [x] Implement a coherent improvement batch, with unit tests where code changes are made.
8. [x] Record any rejected optimization attempts and why they were not kept.

## Phase 4: Full Regression And Wrap

9. [x] Rerun the full baseline matrix.
10. [x] Update specs/journal with the final result and next recommended phase.
11. [x] Commit coherent changes.

## Phase 5: Ranking Quality Follow-Up

12. [x] Diagnose public-web tie cases from the post-context-expansion matrix.
13. [x] Implement a bounded lexical evidence tie-break and plural normalization.
14. [x] Rerun retrieval and answer diagnostics across general web, multi-format, mixed-domain, real manuals, and product-manual answer quality.
15. [x] Commit coherent changes.

## Phase 6: Context Usefulness Follow-Up

16. [x] Diagnose context-pack ordering for answer-bearing chunks under constrained budgets.
17. [x] Implement query-aware context usefulness scoring for first and follow-up context slots.
18. [x] Rerun retrieval and answer diagnostics across general web, multi-format, mixed-domain, real manuals, and product-manual answer quality.
19. [x] Commit coherent changes.

## Phase 7: Context Quality Diagnostic Follow-Up

20. [x] Add a bounded context-quality diagnostic report for real eval suites.
21. [x] Run the diagnostic on general-web and multi-format real knowledge, including constrained token budgets.
22. [x] Implement a safe context-selection rank prior for high-coverage evidence under tight budgets.
23. [x] Rerun retrieval, answer, mixed-domain, real-manual, and product-manual answer-quality diagnostics.
24. [x] Commit coherent changes.

## Phase 8: Budget-Aware Context Compression

25. [x] Add query-aware sentence compaction for long context items.
26. [x] Add adjacent same-source evidence merge for supporting context under tight budgets.
27. [x] Preserve citation/evidence lineage for merged context items.
28. [x] Rerun context-quality diagnostics, retrieval matrix, answer diagnostics, and focused unit tests.
29. [x] Commit coherent changes.

## Phase 9: Release Readiness Gate

30. [x] Add a bounded release-readiness report that consumes retained real-data reports.
31. [x] Classify retrieval, context-quality, and answer-quality stages as passed/warning/failed.
32. [x] Generate JSON and Markdown reports under `.tmp/eval/`.
33. [x] Add unit coverage for pass, warning, missing-report failure, and Markdown writer paths.
34. [x] Commit coherent changes.
