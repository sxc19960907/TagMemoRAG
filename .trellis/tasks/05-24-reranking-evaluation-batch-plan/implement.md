# Implementation Plan

## Checklist

- [x] Create Trellis task.
- [x] Inspect recent release-readiness and GitHub ranking-pressure diagnostics.
- [x] Write reranking evaluation batch plan.
- [x] Start task.
- [x] Validate that existing commands still reproduce the baseline.
- [ ] Commit and archive.

## Validation Commands

```text
.venv/bin/python scripts/release_readiness.py \
  --report general_web_ranking_pressure=.tmp/eval/general-web-ranking-pressure.json \
  --output .tmp/eval/reranking-plan-release-readiness.json
```

```text
.venv/bin/python scripts/diag_general_web_ranking_pressure.py \
  --report .tmp/eval/general-web-after-evidence-refinement.json \
  --output .tmp/eval/reranking-plan-ranking-pressure.json
```

## Rollback

This task is documentation-only. If the plan is wrong, update or revert the task
artifact before archiving; no runtime rollback is needed.
