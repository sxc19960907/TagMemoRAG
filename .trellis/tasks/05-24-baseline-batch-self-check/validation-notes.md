# Validation Notes

## Focused Tests

```text
.venv/bin/pytest \
  tests/unit/test_release_readiness.py \
  tests/unit/test_diag_general_web_ranking_pressure.py \
  tests/unit/test_reranking_eval_gate.py \
  -q
```

Result:

- `22 passed`

## Release Readiness

```text
.venv/bin/python scripts/release_readiness.py \
  --report general_web_ranking_pressure=.tmp/eval/general-web-ranking-pressure.json \
  --output .tmp/eval/program-baseline-release-readiness.json
```

Observed:

- release status: `passed`
- `general_web_retrieval.hit_at_k=1.0`
- `general_web_retrieval.recall_at_k=0.971429`
- `general_web_retrieval.mrr=0.773810`
- `general_web_retrieval.ranking_pressure_count=2`
- `general_web_retrieval.highest_pressure_rank_count=5`

## Reranking Gate

```text
.venv/bin/python scripts/reranking_eval_gate.py \
  --baseline-readiness .tmp/eval/program-baseline-release-readiness.json \
  --candidate-readiness .tmp/eval/program-baseline-release-readiness.json \
  --baseline-ranking-pressure .tmp/eval/general-web-ranking-pressure.json \
  --candidate-ranking-pressure .tmp/eval/general-web-ranking-pressure.json \
  --output .tmp/eval/program-baseline-reranking-gate.json
```

Observed:

- gate status: `passed`
- failed checks: `[]`

## Decision

Baseline is stable. The recommended next child task is to automate this command
sequence into a batch runner so future candidate work starts from one repeatable
self-check rather than manual command stitching.

## Privacy

Generated `.tmp` reports were not staged. This task records only bounded metrics
and statuses.
