# Pilot eval informational policy design

## Boundaries

- Shared diagnosis logic lives in `src/tagmemorag/eval_reauthoring.py`.
- `scripts/diagnose_eval_reauthoring.py` stays a thin script wrapper around the shared module.
- `src/tagmemorag/production_pilot.py` owns pilot stage assembly and status aggregation.
- `src/tagmemorag/cli.py` only parses arguments and passes the normalized option through.

## Data Flow

```
CLI/script --informational-suites
  -> split comma-separated suite names
  -> diagnose_reauthoring(..., informational_suites=...)
  -> SuiteDiagnosis(informational=True|False)
  -> DiagnosisReport.summary()
  -> pilot stage detail
  -> pilot aggregate status
```

## Contracts

`SuiteDiagnosis` gains:

- `informational: bool = False`

This field is additive and does not replace:

- `status`
- `severity`
- metrics and deltas
- `recommendation`
- `reasons`

`DiagnosisReport.summary()` remains backward compatible by preserving:

- `suite_count`
- `status_counts`
- `highest_severity`

It also adds:

- `blocking_status_counts`
- `highest_blocking_severity`
- `informational_count`
- `informational_suites`

`DiagnosisReport.to_stage_detail()` includes the new summary fields so the pilot report can decide warning/pass without reimplementing diagnosis rules.

## CLI Shape

Both entry points use:

```bash
--informational-suites cross_kb_negatives.jsonl,fault_codes.jsonl
```

Empty or omitted means no informational suites.

## Pilot Status

`eval_reauthoring_diagnosis` status is:

- `passed` if `highest_blocking_severity == 0`.
- `warning` if `highest_blocking_severity > 0`.
- `failed` only for invalid baseline input or supplying only one baseline.

Overall pilot status continues to use the existing aggregate rule over stages.

## Compatibility

- Existing JSON consumers that read `highest_severity` or `status_counts` keep the same meaning.
- Existing callers that do not pass `informational_suites` get identical status behavior because all suites remain blocking.
- The diagnosis sorting order still uses original severity and suite name, so top-suite visibility remains stable.

## Operational Notes

The policy is intentionally explicit per run. Operators can make known stress suites informational for a pilot while still seeing their underlying diagnostics in the retained report.
