# Implementation Plan

1. Add `production_provider_verify.py` with shared report types and operator orchestration.
2. Wire `production-provider verify` into `cli.py`.
3. Refactor `scripts/run_production_provider_smoke.py` to delegate to the shared implementation while preserving arguments.
4. Add focused unit tests for shared verify behavior and CLI wiring.
5. Update `docs/production-provider-smoke-runbook.md`.
6. Run targeted tests plus sanitization checks.
