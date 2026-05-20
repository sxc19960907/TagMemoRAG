# Design

## Boundaries

The feature is an entry-point consolidation. It does not change provider smoke internals, pilot scoring, provider probe behavior, Qdrant sync, or S3 blob semantics.

## Module Shape

Add `src/tagmemorag/production_provider_verify.py` as the shared operator orchestration module. It owns:

- `ProductionProviderVerifyReport`
- `VerifyCheck`
- `run_production_provider_verify(...)`
- helper functions for env check, Docker startup, S3 bucket ensure, smoke subprocess invocation, optional pilot invocation, and report writing

`src/tagmemorag/cli.py` adds:

```text
production-provider verify
  --level smoke|pilot
  --check-only
  smoke options
  pilot options
```

`scripts/run_production_provider_smoke.py` becomes a compatibility wrapper over `run_production_provider_verify(level="smoke")`. Its JSON schema remains `production_provider_smoke_runner.v1` for compatibility unless the shared report schema is intentionally versioned to cover both. The wrapper can keep printing the shared report JSON when the fields match.

## Data Flow

```text
CLI/script args
  -> run_production_provider_verify
  -> required env check
  -> optional Docker compose
  -> optional S3 bucket ensure
  -> if level=smoke:
       nested production-provider smoke subprocess
     if level=pilot:
       nested production-provider smoke subprocess
       then run_production_pilot in-process
  -> sanitized report JSON/Markdown
```

The nested smoke remains a subprocess so the operator path verifies the installed CLI entry point. Pilot can run in-process because it is already a product CLI command and its report writer is reusable; tests can inject a fake pilot runner.

## Report Contract

Use a unified schema version such as `production_provider_verify.v1` for the new CLI. Include:

- `status`
- `level`
- `config_path`
- `output_path`
- `checks`
- `smoke_exit_code`
- optional `pilot_status`

Each check includes `name`, `status`, `detail`, and optional `error`. Detail can include command argv with no secret values, output paths, bucket names, exit codes, and status counts.

## Compatibility

- `production-provider smoke` remains unchanged.
- `scripts/run_production_provider_smoke.py` remains valid for existing automation.
- New runbook examples prefer `python -m tagmemorag production-provider verify --level smoke`.

## Validation

Unit tests should avoid network and Docker by injecting fake runners and fake S3 clients where practical. CLI-level tests can call `cli.main([...])` with monkeypatched verify runner.
