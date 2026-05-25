# Implementation Plan

## Steps

- [x] Add `src/tagmemorag/evidence_usefulness_diagnostic.py` with dataclass
      report contracts, JSON/Markdown rendering, report loading, score
      calculation, and privacy-bounded serialization.
- [x] Add `scripts/diag_evidence_usefulness.py` as a thin CLI wrapper.
- [x] Add `tests/unit/test_evidence_usefulness_diagnostic.py`.
- [x] Run focused tests:
      `.venv/bin/pytest tests/unit/test_evidence_usefulness_diagnostic.py tests/unit/test_diag_general_web_ranking_pressure.py tests/unit/test_reranking_gate_batch.py tests/unit/test_reranking_eval_gate.py -q`
- [x] Run a local dry run if retained reports exist:
      `.venv/bin/python scripts/diag_evidence_usefulness.py --report .tmp/eval/general-web-after-evidence-refinement.json --output .tmp/eval/evidence-usefulness-general-web.json`
- [x] Inspect generated JSON for forbidden raw payload keywords.
- [ ] Update the parent program log with results and next recommendation.
- [ ] Commit the child task and related code changes, then archive this child.

## Review Gates

- No runtime retrieval/ranking imports or behavior changes.
- No committed `.tmp/` generated reports.
- No raw query/result text in diagnostic output.
- Existing gate tests remain green.

## Eval Slice

Primary slice: `tests/fixtures/eval/general_web.jsonl` via the retained eval
report `.tmp/eval/general-web-after-evidence-refinement.json` when available.

This task is allowed to pass without reseeding live public-web docs if the
retained report is absent; in that case, unit fixtures provide the deterministic
validation and the parent log records the missing local report.
