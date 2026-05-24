# Design

## Boundary

Add a pure report-comparison module:

- `src/tagmemorag/reranking_eval_gate.py`

Add a script wrapper:

- `scripts/reranking_eval_gate.py`

The module reads already-generated JSON reports. It does not run retrieval,
call providers, import FastAPI, mutate graph state, or write `.tmp` reports
unless the CLI user passes `--output`.

## Inputs

Required:

- `--baseline-readiness`
- `--candidate-readiness`
- `--baseline-ranking-pressure`
- `--candidate-ranking-pressure`

These are JSON files produced by:

- `scripts/release_readiness.py`
- `scripts/diag_general_web_ranking_pressure.py`

## Output Contract

Schema:

```text
reranking_eval_gate.v1
```

Fields:

- `status`: `passed` or `failed`
- `checks`: bounded list of check objects
- `summary`: bounded aggregate baseline/candidate metric values
- `next_steps`: bounded remediation hints when failed

Check objects contain:

- `name`
- `status`
- `baseline`
- `candidate`
- `message`

No raw query text, snippets, vectors, full candidate lists, or generated report
payloads are copied into the output.

## Gate Rules

Fail if:

- candidate release readiness status is not `passed`,
- general-web retrieval `hit_at_k`, `recall_at_k`, or `mrr` decreases,
- `ranking_pressure_count` increases,
- `highest_pressure_rank_count` increases,
- a case present in both ranking-pressure reports has a later
  `first_matched_rank`.

Case-level regression is intentionally limited to cases present in both reports.
If a new pressure case appears, the aggregate pressure count check catches it.

## Markdown

Markdown mirrors JSON with a compact table. It is for human review, not a
machine contract.

## Compatibility

This is additive. Existing release readiness and ranking-pressure scripts are
unchanged.
