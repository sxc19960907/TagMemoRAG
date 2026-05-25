# Validation Notes

## Focused Tests

```text
.venv/bin/pytest \
  tests/unit/test_reranking_gate_batch.py \
  tests/unit/test_reranking_eval_gate.py \
  tests/unit/test_release_readiness.py \
  -q
```

Result:

- `21 passed`

## CLI Self-Check

```text
.venv/bin/python scripts/reranking_gate_batch.py \
  --output-dir .tmp/eval/program-gate-batch
```

Observed:

- batch status: `passed`
- release readiness status: `passed`
- reranking gate status: `passed`
- failed checks: `[]`
- bounded summary check: no `actual_top_k`, `top_results`, raw snippet, or
  private query terms in the batch summary.

Generated reports:

- `.tmp/eval/program-gate-batch/release-readiness.json`
- `.tmp/eval/program-gate-batch/reranking-gate.json`
- `.tmp/eval/program-gate-batch/batch-summary.json`

## Decision

The manual self-check from child 1 is now automated. The recommended next child
is an observational evidence-usefulness dry run that produces a bounded report
without changing retrieval order.

## Privacy

Generated `.tmp` reports were not staged. Committed outputs include only code,
tests, task notes, bounded statuses, metrics, and check names.
