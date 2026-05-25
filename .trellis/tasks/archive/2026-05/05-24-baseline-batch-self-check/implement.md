# Implementation Plan

## Checklist

- [x] Create child task under the long-horizon parent.
- [x] Capture requirements.
- [x] Start task.
- [x] Run focused tests.
- [x] Run release readiness self-check.
- [x] Run reranking gate self-check.
- [x] Record validation notes.
- [x] Update parent program log.
- [ ] Commit and archive child.

## Validation Commands

```text
.venv/bin/pytest \
  tests/unit/test_release_readiness.py \
  tests/unit/test_diag_general_web_ranking_pressure.py \
  tests/unit/test_reranking_eval_gate.py \
  -q
```

```text
.venv/bin/python scripts/release_readiness.py \
  --report general_web_ranking_pressure=.tmp/eval/general-web-ranking-pressure.json \
  --output .tmp/eval/program-baseline-release-readiness.json
```

```text
.venv/bin/python scripts/reranking_eval_gate.py \
  --baseline-readiness .tmp/eval/program-baseline-release-readiness.json \
  --candidate-readiness .tmp/eval/program-baseline-release-readiness.json \
  --baseline-ranking-pressure .tmp/eval/general-web-ranking-pressure.json \
  --candidate-ranking-pressure .tmp/eval/general-web-ranking-pressure.json \
  --output .tmp/eval/program-baseline-reranking-gate.json
```
