# Production Provider Unified Verify CLI

## Goal

Expose a single product CLI entry point for production-provider verification so operators can run smoke and pilot gates without remembering separate scripts or runbook command chains.

## Requirements

- Add `python -m tagmemorag production-provider verify` as the canonical verification command.
- Support at least two levels:
  - `smoke`: existing local-live provider smoke path with env check, Docker Qdrant/MinIO startup, S3 bucket ensure, Qdrant reset, and nested production-provider smoke.
  - `pilot`: smoke plus production pilot gate using configurable suite/docs/baselines and retained output.
- Keep existing `production-provider smoke` command behavior intact.
- Keep `scripts/run_production_provider_smoke.py` available as a backwards-compatible thin wrapper.
- Reports must be sanitized:
  - no secret values
  - no Authorization headers
  - no raw provider responses
  - no raw answer bodies, retrieved excerpts, vectors, or source text
- The command must work without live provider calls in tests by allowing subprocess/provider-adjacent work to be mocked.
- Document the unified command in the provider smoke runbook.

## Acceptance Criteria

- [x] `production-provider verify --level smoke --check-only` performs required env, Docker, and S3 checks without running nested smoke.
- [x] `production-provider verify --level smoke` invokes the existing nested `production-provider smoke` path and returns non-zero on failure.
- [x] `production-provider verify --level pilot` runs the smoke gate first and only runs pilot when smoke passes.
- [x] Pilot options include suite/docs, thresholds, hashing/production baselines, informational suites, accepted suites, workdir, output, and format.
- [x] The legacy script delegates to the shared verify implementation and existing script unit tests remain meaningful.
- [x] Unit tests cover smoke success/failure, check-only, pilot gating, output writing, and sanitized command shape.
- [x] Runbook documents the unified command and labels the legacy script as compatibility.
