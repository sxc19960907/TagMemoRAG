# Implementation Plan

## Checklist

- [x] Create Trellis task and capture scope.
- [x] Start task.
- [x] Update README eval guidance.
- [x] Update eval baseline workflow docs.
- [x] Run documentation-focused validation.
- [ ] Commit and archive.

## Validation Commands

```text
rg -n "reranking evaluation gate|reranking_eval_gate|ranking pressure" README.md docs/eval-baseline-workflow.md
```

```text
.venv/bin/python scripts/reranking_eval_gate.py \
  --baseline-readiness .tmp/eval/release-readiness-with-ranking-pressure.json \
  --candidate-readiness .tmp/eval/release-readiness-with-ranking-pressure.json \
  --baseline-ranking-pressure .tmp/eval/general-web-ranking-pressure.json \
  --candidate-ranking-pressure .tmp/eval/general-web-ranking-pressure.json \
  --format markdown
```

## Rollback

Revert the documentation additions. No runtime behavior is changed.
