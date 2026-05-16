# Implementation Plan

## Checklist

- [x] Add config fields and validation for residual enablement / Top-N.
- [x] Add intrinsic residual training module with SQLite upsert helper and tests.
- [x] Wire rebuild fail-soft report fields and CLI `retrain-residuals`.
- [x] Add registry residual loader for online consumers.
- [x] Add residual prior support to `ResidualPyramid`.
- [x] Wire `apply_tag_boost` to pass residuals into Pyramid and spike only when enabled.
- [x] Add metrics and label contract updates.
- [x] Run focused unit tests plus baseline invariance smoke.

## Validation

- `pytest tests/unit/test_tag_intrinsic_residuals.py tests/unit/test_residual_pyramid.py tests/unit/test_wave_tag_spike_propagate.py tests/unit/test_apply_tag_boost.py tests/unit/test_phase1_rebuild_cooccurrence.py tests/unit/test_observability_metrics.py tests/unit/test_cli.py`
- `pytest tests/e2e/test_search_baseline_invariance.py`

## Review Gates

- Confirm default config leaves existing tests / baselines unchanged.
- Confirm all new metric labels are in the allowed label set and avoid high-cardinality values.
