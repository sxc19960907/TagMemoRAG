# Implementation Plan

## Checklist

- [x] Activate the task.
- [x] Add `scripts/diag_general_web_ranking_pressure.py`.
- [x] Add unit tests for report generation, markdown rendering, privacy, and CLI
      output.
- [x] Run the diagnostic against the retained general-web report.
- [x] Run focused tests.
- [x] Record validation notes.
- [x] Commit and archive.

## Validation Commands

```text
.venv/bin/python scripts/diag_general_web_ranking_pressure.py \
  --report .tmp/eval/general-web-after-evidence-refinement.json \
  --output .tmp/eval/general-web-ranking-pressure.json
```

```text
.venv/bin/pytest \
  tests/unit/test_diag_general_web_ranking_pressure.py \
  tests/unit/test_summarize_eval_case_review.py \
  -q
```

## Risk Points

- Reports must stay bounded and avoid raw snippets.
- This task must not change scoring code or fixtures.
- Ranking-pressure classification must not label top-k misses as solved; it only
  identifies cases where expected evidence is reachable but under-ranked.
