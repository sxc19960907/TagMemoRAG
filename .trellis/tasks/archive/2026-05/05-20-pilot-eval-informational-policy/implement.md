# Pilot eval informational policy implementation plan

## Checklist

- [x] Update shared diagnosis dataclasses, summaries, JSON, Markdown, and stage detail.
- [x] Add `--informational-suites` to `scripts/diagnose_eval_reauthoring.py`.
- [x] Thread informational suites through `run_production_pilot` and `tagmemorag pilot run`.
- [x] Update unit tests for diagnosis, script CLI, pilot service, and CLI wiring.
- [x] Update pilot/eval docs with the recommended stress-test suite list.
- [x] Run focused tests and one real pilot command.
- [x] Run `git diff --check`.
- [ ] Archive the task, record the journal, and commit.

## Validation Commands

```bash
uv run pytest tests/unit/test_production_pilot.py tests/unit/test_diagnose_eval_reauthoring.py tests/unit/test_cli.py -q
uv run python -m tagmemorag pilot run --config examples/config/local-hashing-npz.yaml --suite tests/fixtures/eval/coffee.jsonl --docs tests/fixtures --hashing-baseline tests/fixtures/eval/baselines/hashing.json --production-baseline tests/fixtures/eval/baselines/siliconflow.json --informational-suites cross_kb_negatives.jsonl,fault_codes.jsonl,model_numbers.jsonl,tag_cooccurrence.jsonl --workdir .tmp/pilot-info-policy
git diff --check
```

## Risk / Rollback

- Risk: treating informational suites as hidden passes. Mitigation: preserve original status/severity and add explicit `informational` markers in all outputs.
- Risk: breaking JSON consumers. Mitigation: add fields only; do not rename existing fields.
- Rollback point: revert edits in `eval_reauthoring.py`, `production_pilot.py`, `cli.py`, script wrapper, tests, and docs.
