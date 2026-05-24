# Validation Notes

## Change

Updated `.trellis/spec/backend/architecture.md` to record the 2026-05-24
release-readiness baseline after the general-web evidence label refinement.

The spec now states:

- retained readiness report:
  `.tmp/eval/release-readiness-after-evidence-refinement.json`
- release readiness status: `passed`
- `general_web_retrieval` metrics:
  - `hit@k=1.0`
  - `recall_at_k=0.971429`
  - `MRR=0.773810`
- previous warning baseline:
  - `hit@k=1.0`
  - `recall_at_k=0.928571`
  - `MRR=0.651361`

It also records that this was an eval-label correction rather than a runtime
retrieval-scoring change, and that GitHub Hello World cases remain future
ranking pressure.

## Validation

```text
.venv/bin/python scripts/release_readiness.py \
  --output .tmp/eval/release-readiness-after-baseline-refresh.json
```

Result:

- status: `passed`
- non-passed stages: `[]`

```text
.venv/bin/pytest tests/unit/test_release_readiness.py -q
```

Result:

- `4 passed`
