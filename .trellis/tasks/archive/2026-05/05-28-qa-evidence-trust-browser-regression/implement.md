# QA Evidence Trust and Browser Regression Implementation Plan

## Checklist

- [x] Read Trellis backend/frontend-relevant specs before editing.
- [x] Add safe provenance fields to retrieval evidence.
- [x] Preserve/sanitize provenance in QA page session history.
- [x] Render provenance, page range, OCR marker, and strength labels in QA Sources cards.
- [x] Add/adjust static UI tests for the QA page asset.
- [x] Add browser regression for citation/source inspection and user black-box flow.
- [x] Run focused tests:
  - QA UI static tests
  - retrieval/answer unit tests touched by evidence contract
  - relevant browser integration tests
- [x] Run CI-equivalent unit/e2e and eval gates.
- [x] Update task acceptance and verification notes.
- [ ] Commit, archive, and journal.

## Verification Results

- Focused unit/UI: 66 passed.
- Browser QA regression subset: 4 passed.
- CI unit/e2e gate: 1282 passed.
- Eval gate: all 8 eval suites passed.

## Risk Points

- Evidence payload must not leak raw debug fields or unsafe storage identifiers.
- Browser tests can become brittle if they assert incidental copy; prefer stable visible labels and behavior.
- DOCX display source differs from indexed source; tests should assert both are understandable, not that one replaces the other globally.

## Rollback

- If provenance rendering creates layout issues, keep backend additive fields and simplify front-end labels.
- If browser regression grows too broad, split into a smaller trust-flow test plus focused existing tests.
