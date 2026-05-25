# Implementation Plan

- [x] Create child task.
- [x] Define requirements and design.
- [x] Read active task and relevant backend specs.
- [x] Extend manifest summary module with optional rerun execution.
- [x] Extend CLI with `--rerun`.
- [x] Add focused tests for rerun behavior.
- [x] Run focused tests and CLI smoke.
- [x] Update parent program log.
- [ ] Commit and archive this child task.

## Verification

- Focused tests:
  `.venv/bin/pytest tests/unit/test_default_on_retained_monitoring.py -q`
  returned `9 passed`.
- Related gate tests:
  `.venv/bin/pytest tests/unit/test_default_on_retained_monitoring.py tests/unit/test_reranking_gate_batch.py tests/unit/test_reranking_eval_gate.py tests/unit/test_release_readiness.py -q`
  returned `34 passed`.
- Summary-only CLI smoke:
  `.venv/bin/python scripts/default_on_retained_monitoring.py --manifest examples/default-on-retained-monitoring.json --output .tmp/eval/default-on-retained-monitoring-summary.json`
  returned exit code `0`.
