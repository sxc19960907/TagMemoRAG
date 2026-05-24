# Implementation Plan

## Steps

- [x] Add `src/tagmemorag/same_page_ordering_diagnostic.py`.
- [x] Add `scripts/diag_same_page_ordering.py`.
- [x] Add `tests/unit/test_same_page_ordering_diagnostic.py`.
- [x] Run focused tests:
      `.venv/bin/pytest tests/unit/test_same_page_ordering_diagnostic.py tests/unit/test_evidence_usefulness_diagnostic.py tests/unit/test_diag_general_web_ranking_pressure.py tests/unit/test_reranking_gate_batch.py tests/unit/test_reranking_eval_gate.py -q`
- [x] Run retained-report dry run:
      `.venv/bin/python scripts/diag_same_page_ordering.py --report .tmp/eval/general-web-after-evidence-refinement.json --output .tmp/eval/same-page-ordering-general-web.json`
- [x] Inspect generated report for forbidden raw payload markers.
- [x] Run the batch gate.
- [ ] Update the parent program log with result and next recommendation.
- [ ] Commit and archive this child.

## Review Gates

- No runtime retrieval/ranking behavior change.
- No generated `.tmp/` files committed.
- No raw query/result text in output.
- Existing adjacent tests and batch gate remain green.

## Eval Slice

Primary slice: retained report for `tests/fixtures/eval/general_web.jsonl`,
especially `github-hello-world-repository` and
`github-hello-world-pull-request`.
