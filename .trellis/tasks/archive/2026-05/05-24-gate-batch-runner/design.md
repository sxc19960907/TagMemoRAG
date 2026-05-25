# Design

## Boundary

Add:

- `src/tagmemorag/reranking_gate_batch.py`
- `scripts/reranking_gate_batch.py`

The module orchestrates existing report readers/writers:

- `tagmemorag.release_readiness`
- `tagmemorag.reranking_eval_gate`

It does not run retrieval, fetch web pages, call providers, or mutate any
runtime KB state.

## Inputs

Defaults should match retained baseline paths:

- `general_web_ranking_pressure=.tmp/eval/general-web-ranking-pressure.json`
- `baseline_readiness` and `candidate_readiness` are the generated readiness
  report from the batch self-check unless explicitly provided.
- `baseline_ranking_pressure` and `candidate_ranking_pressure` default to the
  same retained ranking-pressure path.

CLI options:

- `--output-dir`
- `--general-web-ranking-pressure`
- `--baseline-readiness`
- `--candidate-readiness`
- `--baseline-ranking-pressure`
- `--candidate-ranking-pressure`
- `--format json|markdown` for the batch summary

## Outputs

Under `--output-dir`:

- `release-readiness.json`
- `reranking-gate.json`
- `batch-summary.json` or `batch-summary.md`

Schema:

```text
reranking_gate_batch.v1
```

Summary fields:

- `status`
- `release_readiness_status`
- `reranking_gate_status`
- `reports`
- `failed_checks`
- `next_steps`

## Status Rules

Batch `status=passed` only when:

- release readiness is `passed`, and
- reranking gate is `passed`.

Otherwise `status=failed`.

## Privacy

The batch summary copies only bounded statuses, counts, and check names. It
does not copy full child report payloads.
