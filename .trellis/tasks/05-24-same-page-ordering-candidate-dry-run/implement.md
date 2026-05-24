# Implementation Plan

## Steps

- [x] Add `src/tagmemorag/same_page_ordering_candidate.py`.
- [x] Add `scripts/diag_same_page_candidate.py`.
- [x] Add `tests/unit/test_same_page_ordering_candidate.py`.
- [x] Run focused tests:
      `.venv/bin/pytest tests/unit/test_same_page_ordering_candidate.py tests/unit/test_same_page_ordering_diagnostic.py tests/unit/test_evidence_usefulness_diagnostic.py tests/unit/test_reranking_gate_batch.py tests/unit/test_reranking_eval_gate.py -q`
- [x] Run retained-report dry run:
      `.venv/bin/python scripts/diag_same_page_candidate.py --report .tmp/eval/general-web-after-evidence-refinement.json --output .tmp/eval/same-page-candidate-general-web.json`
- [x] Generate a candidate ranking-pressure report if needed for the reranking gate.
- [x] Run batch gate.
- [x] Inspect generated JSON/Markdown for forbidden raw payload markers.
- [ ] Update parent program log with result and next recommendation.
- [ ] Commit and archive this child.

## Review Gates

- No runtime retrieval or ranking behavior change.
- No generated `.tmp/` files committed.
- No raw query/result text in output.
- Adjacent tests and batch gates remain green.

## Eval Slice

Primary slice: retained report for `tests/fixtures/eval/general_web.jsonl`.
The key cases are `github-hello-world-repository` and
`github-hello-world-pull-request`, but regression checks must cover every case
present in the retained report.
