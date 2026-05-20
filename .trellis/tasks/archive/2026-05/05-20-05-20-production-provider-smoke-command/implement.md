# Implementation Plan

## Steps

1. Add `production_provider_smoke.py` with sanitized report contracts and orchestration helpers.
2. Wire `tagmemorag production-provider smoke` in `cli.py`.
3. Add unit tests for report shape, sidecar import preparation, answer sanitization, and CLI wiring.
4. Run focused tests, then the broader quality gate if time allows.

## Validation

- `uv run pytest tests/unit/test_production_provider_smoke.py tests/unit/test_cli.py`
- `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py`
