# Implementation Plan

## Checklist

- [x] Activate the task.
- [x] Add optional ranking-pressure report handling in
      `src/tagmemorag/release_readiness.py`.
- [x] Add unit tests for present and missing optional report behavior.
- [x] Run focused tests and the release-readiness script with the retained
      ranking-pressure report.
- [x] Record validation notes.
- [ ] Commit and archive.

## Validation Commands

```text
.venv/bin/pytest tests/unit/test_release_readiness.py -q
```

```text
.venv/bin/python scripts/release_readiness.py \
  --report general_web_ranking_pressure=.tmp/eval/general-web-ranking-pressure.json \
  --output .tmp/eval/release-readiness-with-ranking-pressure.json
```
