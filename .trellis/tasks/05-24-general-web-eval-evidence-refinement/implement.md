# Implementation Plan

## Checklist

- [x] Activate the task.
- [x] Update the MDN `general_web.jsonl` relevant entries with narrowly scoped
      useful evidence.
- [x] Run fixture/unit validation.
- [x] Rerun general-web retrieval with seeded docs and compare metrics.
- [x] Record metric impact and rationale in task notes.
- [x] Commit only the fixture and task artifacts.

## Validation Commands

```text
.venv/bin/pytest tests/unit/test_run_eval_ci.py -q
```

```text
.venv/bin/python -m tagmemorag eval run \
  --suite tests/fixtures/eval/general_web.jsonl \
  --docs .tmp/general-web-eval/general_web \
  --config examples/config/local-hashing-npz.yaml \
  --kb general_web \
  --top-k 8 \
  --min-recall-at-k 0.0 --min-mrr 0.0 --min-hit-at-k 0.0 \
  --output .tmp/eval/general-web-after-evidence-refinement.json
```

## Risk Points

- Adding unmatched expected entries lowers recall, so every new entry must match
  a useful current top-k chunk.
- Broadening GitHub expectations would hide real ranking issues; do not do that
  in this task.
- `.tmp/` outputs are validation artifacts and should remain uncommitted.
