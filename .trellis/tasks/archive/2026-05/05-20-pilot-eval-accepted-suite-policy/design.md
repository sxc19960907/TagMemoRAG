# Pilot eval accepted suite policy design

## Boundaries

- Shared policy marking lives in `src/tagmemorag/eval_reauthoring.py`.
- Script and package CLIs parse comma-separated suite names only.
- `production_pilot.py` consumes report summary fields and does not duplicate classification logic.

## Contract Additions

`SuiteDiagnosis` gains:

- `accepted: bool = False`

Existing fields keep their meaning:

- `status`
- `severity`
- `informational`
- metrics/deltas/recommendation/reasons

`DiagnosisReport.summary()` adds:

- `accepted_count`
- `accepted_suites`

`blocking_status_counts` and `highest_blocking_severity` exclude suites where either `informational` or `accepted` is true.

## CLI Shape

Both diagnosis and pilot entry points support:

```bash
--accepted-suites product_manuals.jsonl,mixed_language.jsonl,tag_rerank_edge.jsonl
```

This can be combined with:

```bash
--informational-suites cross_kb_negatives.jsonl,fault_codes.jsonl,model_numbers.jsonl,tag_cooccurrence.jsonl
```

## Current Recommended Policy

- Informational stress-test suites: `cross_kb_negatives.jsonl`, `fault_codes.jsonl`, `model_numbers.jsonl`, `tag_cooccurrence.jsonl`.
- Accepted reviewed suites: `product_manuals.jsonl`, `mixed_language.jsonl`, `tag_rerank_edge.jsonl`.
- `coffee.jsonl` remains unaccepted by default because the latest aggregate diagnosis still flags monitor-level divergence after Phase A.

## Compatibility

- Existing consumers that read `highest_severity`, `status_counts`, or original per-suite status retain the same data.
- Existing callers that do not pass accepted suites get identical behavior.
- Markdown adds an Accepted column; JSON adds fields.
