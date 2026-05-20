# Pilot eval gate diagnosis design

## Boundary

The change is a report integration. It does not run production embedder eval, refresh baselines, or edit fixtures.

In scope:

- Shared module `src/tagmemorag/eval_reauthoring.py`
- Update `scripts/diagnose_eval_reauthoring.py` to reuse the shared module
- Optional pilot diagnosis stage in `src/tagmemorag/production_pilot.py`
- CLI flags and docs/tests

Out of scope:

- Case-level review summaries inside pilot report
- Live provider calls for diagnosis
- Making SiliconFlow a CI gate

## Data Flow

```text
pilot run --hashing-baseline A --production-baseline B
  -> run_production_pilot(... baseline paths ...)
     -> diagnose_eval_reauthoring(A, B)
     -> PilotStage("eval_reauthoring_diagnosis", "warning"|"passed")
```

The existing standalone script becomes a thin CLI wrapper around the shared module.

## Stage Contract

Stage name: `eval_reauthoring_diagnosis`

Detail fields:

- `schema_version`
- `hashing_embedder`
- `production_embedder`
- `suite_count`
- `status_counts`
- `highest_severity`
- `top_suites`: up to five `{suite, status, severity, recommendation, reasons}`

Status:

- `passed`: all suites are `ok` or no review signal.
- `warning`: any suite is `monitor`, `reauthor`, or `investigate`.
- `failed`: only if the baseline inputs cannot be loaded or parsed.

The overall pilot aggregate should treat warning as warning, not failed, unless another required stage fails.

## CLI

`tagmemorag pilot run` gains:

- `--hashing-baseline <path>`
- `--production-baseline <path>`

Both are optional. If only one is supplied, pilot returns failed diagnosis stage with bounded error. If neither is supplied, no diagnosis stage is added.

## Privacy

The diagnosis stage uses baseline aggregate metrics only. It does not include case query text, snippets, actual top-k candidates, or full baseline payloads.
