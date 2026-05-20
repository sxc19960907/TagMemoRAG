# Pilot eval gate diagnosis implementation plan

## Checklist

- [x] Extract diagnosis dataclasses/helpers into `src/tagmemorag/eval_reauthoring.py`.
- [x] Update `scripts/diagnose_eval_reauthoring.py` and its tests to import shared module.
- [x] Add optional diagnosis stage to `run_production_pilot`.
- [x] Wire `tagmemorag pilot run --hashing-baseline --production-baseline`.
- [x] Update tests and docs.
- [x] Run pilot command with baseline flags, focused pytest, and `git diff --check`.
- [ ] Archive task and commit work, archive, and journal.

## Validation Commands

```bash
uv run python -m tagmemorag pilot run \
  --config examples/config/local-hashing-npz.yaml \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --hashing-baseline tests/fixtures/eval/baselines/hashing.json \
  --production-baseline tests/fixtures/eval/baselines/siliconflow.json \
  --workdir .tmp/pilot-eval-gate

uv run pytest tests/unit/test_production_pilot.py tests/unit/test_diagnose_eval_reauthoring.py tests/unit/test_cli.py -q

git diff --check
```

## Rollback Points

- If shared-module extraction creates import churn, keep script code and add a small internal pilot-only summary loader.
- If warning semantics are confusing, keep the stage informational but document that overall pilot status can be warning.
