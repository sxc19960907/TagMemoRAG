# Implementation Plan

- [x] Move ranking-pressure diagnostic logic into
  `src/tagmemorag/general_web_ranking_pressure.py`.
- [x] Keep `scripts/diag_general_web_ranking_pressure.py` as a thin wrapper.
- [x] Add `candidate_eval_report_path` support to
  `run_reranking_gate_batch`.
- [x] Add `--candidate-eval-report` to `scripts/reranking_gate_batch.py`.
- [x] Update unit tests for batch derivation, precedence, CLI wiring, and
  privacy omissions.
- [x] Run focused tests:
  `.venv/bin/pytest tests/unit/test_diag_general_web_ranking_pressure.py tests/unit/test_reranking_gate_batch.py tests/unit/test_reranking_eval_gate.py -q`
- [x] If local `.tmp/eval/same-page-enabled-general-web.json` exists, run the
  batch with `--candidate-eval-report` and confirm it passes.
- [x] Update the parent program log with Child 8 result.
- [x] Commit the child implementation.
- [ ] Archive this child task.
