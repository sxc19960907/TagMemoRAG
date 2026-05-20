# Production verification report command design

## Boundary

Add `scripts/production_verify.py` as an operator script. Keep runtime modules unchanged unless tests reveal an existing helper should be reused.

## Data Flow

```
args
  -> validate_config(config)
  -> run_readiness_smoke(workdir=<report-dir>/readiness, keep_workdir=True)
  -> run_production_pilot(..., output stays embedded in aggregate)
  -> optionally run_provider_probe(config, selected=...)
  -> VerificationReport.to_json/to_markdown
```

## Defaults

- `--config examples/config/local-hashing-npz.yaml`
- `--suite tests/fixtures/eval/coffee.jsonl`
- `--docs tests/fixtures`
- `--workdir .tmp/production-verification`
- no live provider probes unless `--probe` or `--probe all` is supplied
- JSON output by default

## Report Contract

Top-level fields:

- `schema_version`
- `status`
- `config_path`
- `workdir`
- `steps`
- `next_steps`

Step fields:

- `name`
- `status`
- `detail`
- optional `error`

Allowed details are bounded summaries and artifact paths. Reuse existing report `to_dict()` outputs only after narrowing to safe summary fields where needed.

## Status Aggregation

- `failed` if any required deterministic step fails.
- `warning` if pilot is warning or config validation is warning.
- `passed` otherwise.
- Optional provider probe failures make the aggregate `failed` because the operator explicitly requested live validation.
