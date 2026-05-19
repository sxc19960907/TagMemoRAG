# Production pilot runbook implementation plan

## Checklist

- [x] Add production pilot report dataclasses and orchestration in `src/tagmemorag/production_pilot.py`.
- [x] Wire `tagmemorag pilot run` into `src/tagmemorag/cli.py`.
- [x] Add focused unit tests for report sanitization, Markdown rendering, failure aggregation, and CLI output/file behavior.
- [x] Add `docs/production-pilot-runbook.md` and link it from README / operations docs.
- [x] Run local pilot command, focused pytest, and `git diff --check`.
- [ ] Archive task and commit implementation + archive + journal.

## Validation Commands

```bash
uv run python -m tagmemorag pilot run \
  --config examples/config/local-hashing-npz.yaml \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --workdir .tmp/production-pilot-check

uv run pytest tests/unit/test_cli.py tests/unit/test_config_env.py tests/unit/test_production_pilot.py -q

git diff --check
```

## Rollback Points

- If the full orchestration is brittle, keep docs and reduce CLI scope to a report-only wrapper around existing commands.
- If eval fixture thresholds fail unexpectedly, diagnose fixture/config drift before relaxing thresholds.
