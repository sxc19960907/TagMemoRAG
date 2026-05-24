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
11. [ ] Commit coherent changes.
