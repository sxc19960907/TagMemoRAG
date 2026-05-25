# Implementation Plan

- [x] Create child task.
- [x] Read backend and guide specs before code edits.
- [x] Search for same-page config call sites and expected snapshots.
- [x] Change the config default only.
- [x] Update default/snapshot tests for default-on behavior.
- [x] Add or verify explicit false override coverage.
- [x] Run focused tests and stability gates.
- [x] Update parent program log with result.
- [ ] Commit the child artifacts and code changes.
- [ ] Archive this child task.

## Verification

- Focused default/override tests:
  `.venv/bin/pytest tests/unit/test_config_env.py tests/unit/test_eval_runner.py tests/unit/test_retrieval.py -q`
  returned `83 passed`.
- Full related stability tests:
  `.venv/bin/pytest tests/unit/test_config_env.py tests/unit/test_eval_runner.py tests/unit/test_retrieval.py tests/unit/test_reranking_gate_batch.py tests/unit/test_reranking_eval_gate.py tests/unit/test_release_readiness.py -q`
  returned `108 passed`.
- Default-on general-web eval:
  `.venv/bin/python -m tagmemorag eval run --suite tests/fixtures/eval/general_web.jsonl --docs .tmp/general-web-eval/general_web --config examples/config/local-hashing-npz.yaml --kb general_web --top-k 5 --output .tmp/eval/default-on-general-web.json`
  returned `cases=7`, `recall@k=0.971429`, `mrr=1.000000`, and
  `hit@k=1.000000`.
- Candidate-aware gate batch:
  `.venv/bin/python scripts/reranking_gate_batch.py --output-dir .tmp/eval/default-on-implementation-gate --candidate-eval-report .tmp/eval/default-on-general-web.json`
  returned `status=passed`, release readiness `passed`, reranking gate
  `passed`, and failed checks `[]`.
