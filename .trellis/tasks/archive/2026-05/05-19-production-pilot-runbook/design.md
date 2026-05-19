# Production pilot runbook design

## Boundaries

The new pilot flow is an orchestration layer. It must call existing contracts rather than reimplementing validation, provider connectivity, readiness smoke, or eval logic.

In scope:

- `src/tagmemorag/production_pilot.py` as the service/reporting layer.
- `tagmemorag pilot run` CLI wiring.
- Documentation for a small production pilot sequence.
- Unit tests for the report contract and CLI.

Out of scope:

- New retrieval algorithms, new provider adapters, or production observability backends.
- Persisting raw eval reports as part of the pilot summary.
- Making provider probes run automatically against external services beyond the existing explicit `--all` probe semantics.

## Data Flow

```text
CLI args
  -> run_production_pilot(...)
     -> validate_config(config)
     -> run_provider_probe(config, selected={"all"})
     -> run_readiness_smoke(workdir=<pilot>/readiness, keep_workdir=True)
     -> load_config(config) + run_eval(suite, docs, eval_data_dir=<pilot>/eval)
     -> ProductionPilotReport
  -> JSON or Markdown stdout/file
```

## Report Contract

`ProductionPilotReport.to_dict()` returns:

- `schema_version`: `production_pilot.v1`
- `status`: `passed`, `warning`, or `failed`
- `config_path`, `suite_path`, `docs_path`, `workdir`
- `stages`: list of sanitized stage summaries
- `next_steps`: operator guidance strings

Each stage has `name`, `status`, `detail`, and optional `error`. Details may include counts, profile names, provider names, and numeric eval metrics. Details must not include raw queries, candidate snippets, vectors, full source-file lists, API keys, or environment variable values.

## Stage Semantics

- `config_validate`: `failed` fails the pilot. `warning` keeps the pilot in warning unless a later stage fails.
- `provider_probe`: `failed` fails the pilot. `skipped` is allowed for local/offline profiles and does not fail by itself.
- `readiness_smoke`: must pass.
- `eval`: must pass thresholds. The default thresholds follow `eval run` defaults.

## CLI Shape

`tagmemorag pilot run` accepts:

- `--config`, default `examples/config/local-hashing-npz.yaml`
- `--suite`, default `tests/fixtures/eval/coffee.jsonl`
- `--docs`, default `tests/fixtures`
- `--workdir`, optional; defaults to a temporary retained pilot directory
- `--output`, optional
- `--format`, `json` or `markdown`
- eval override flags for `--top-k`, `--source-k`, `--min-recall-at-k`, `--min-mrr`, and `--min-hit-at-k`

The command exits `0` for `passed` or `warning`, `1` for `failed`, and `2` for invalid input/runtime exceptions that prevent producing a report.

## Compatibility

The pilot command uses defaults that are deterministic and network-free. Existing commands keep their current behavior. The new report schema is additive and versioned so future pilot checks can be appended without changing existing consumers.
