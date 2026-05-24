# Implementation Plan

## Checklist

- [x] Create Trellis task and planning artifacts.
- [x] Start task.
- [x] Add `src/tagmemorag/reranking_eval_gate.py`.
- [x] Add `scripts/reranking_eval_gate.py`.
- [x] Add unit tests for pass/fail gates and output privacy.
- [x] Run focused tests.
- [x] Run CLI against retained baseline reports.
- [ ] Commit and archive.

## Validation Commands

```text
.venv/bin/pytest \
  tests/unit/test_reranking_eval_gate.py \
  tests/unit/test_release_readiness.py \
  tests/unit/test_diag_general_web_ranking_pressure.py \
  -q
```

```text
.venv/bin/python scripts/reranking_eval_gate.py \
  --baseline-readiness .tmp/eval/release-readiness-with-ranking-pressure.json \
  --candidate-readiness .tmp/eval/release-readiness-with-ranking-pressure.json \
  --baseline-ranking-pressure .tmp/eval/general-web-ranking-pressure.json \
  --candidate-ranking-pressure .tmp/eval/general-web-ranking-pressure.json \
  --output .tmp/eval/reranking-eval-gate-self-check.json
```

## Rollback

Remove the new module, script, and focused tests. No runtime search behavior is
changed.
