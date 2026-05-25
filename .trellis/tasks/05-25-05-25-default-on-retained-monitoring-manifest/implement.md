# Implementation Plan

- [x] Create child task.
- [x] Define requirements and design.
- [x] Read backend guidelines before code edits.
- [x] Add default manifest.
- [x] Add package summary module.
- [x] Add CLI wrapper.
- [x] Add focused unit tests.
- [x] Run focused tests and CLI smoke.
- [x] Update parent program log.
- [ ] Commit and archive this child task.

## Verification

- Focused tests:
  `.venv/bin/pytest tests/unit/test_default_on_retained_monitoring.py -q`
  returned `6 passed`.
- Related gate tests:
  `.venv/bin/pytest tests/unit/test_default_on_retained_monitoring.py tests/unit/test_reranking_gate_batch.py tests/unit/test_reranking_eval_gate.py tests/unit/test_release_readiness.py -q`
  returned `31 passed`.
- CLI smoke:
  `.venv/bin/python scripts/default_on_retained_monitoring.py --manifest examples/default-on-retained-monitoring.json --output .tmp/eval/default-on-retained-monitoring-summary.json`
  returned exit code `0`.
- Real retained summary: status `passed`, failed checks `[]`; slices:
  general-web `7`, mixed-domain `4`, multiformat `3`, realmanuals `10`.
- Artifact privacy scan over the manifest, package module, CLI wrapper, and
  Trellis task documents returned no forbidden markers checked by this task.
