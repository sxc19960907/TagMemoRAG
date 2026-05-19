# Production embedder eval reauthoring implementation plan

## Checklist

- [x] Implement `scripts/diagnose_eval_reauthoring.py` with pure helper functions and CLI.
- [x] Add tests in `tests/unit/test_diagnose_eval_reauthoring.py`.
- [x] Update README and `docs/eval-baseline-workflow.md`.
- [x] Run the diagnostic against committed hashing/siliconflow baselines and inspect the result.
- [x] Run focused tests and `git diff --check`.
- [ ] Archive task and commit work, archive, and journal.

## Validation Commands

```bash
uv run python scripts/diagnose_eval_reauthoring.py --format markdown

uv run pytest tests/unit/test_diagnose_eval_reauthoring.py tests/unit/test_build_eval_baseline.py -q

git diff --check
```

## Rollback Points

- If the classification feels too opinionated, keep the metric delta report and remove the recommendation/status fields.
- If script discoverability is weak, wire a later `tagmemorag eval diagnose` command in a separate task.
