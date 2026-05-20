# Pilot eval accepted suite policy implementation plan

## Checklist

- [x] Extend shared diagnosis dataclasses, summary, JSON, Markdown, and stage detail with accepted-suite fields.
- [x] Expose `--accepted-suites` in `scripts/diagnose_eval_reauthoring.py`.
- [x] Thread accepted suites through `run_production_pilot` and `tagmemorag pilot run`.
- [x] Update unit tests for diagnosis, script CLI, pilot service, and CLI wiring.
- [x] Update docs with the current accepted-suite recommendation.
- [x] Run focused tests and real pilot commands.
- [x] Run `git diff --check`.
- [ ] Commit, archive, and journal.

## Validation Commands

```bash
uv run pytest tests/unit/test_production_pilot.py tests/unit/test_diagnose_eval_reauthoring.py tests/unit/test_cli.py -q
uv run python -m tagmemorag pilot run --config examples/config/local-hashing-npz.yaml --suite tests/fixtures/eval/coffee.jsonl --docs tests/fixtures --hashing-baseline tests/fixtures/eval/baselines/hashing.json --production-baseline tests/fixtures/eval/baselines/siliconflow.json --informational-suites cross_kb_negatives.jsonl,fault_codes.jsonl,model_numbers.jsonl,tag_cooccurrence.jsonl --accepted-suites product_manuals.jsonl,mixed_language.jsonl,tag_rerank_edge.jsonl --workdir .tmp/pilot-accepted-policy
git diff --check
```

## Risk / Rollback

- Risk: accepted suites hide review debt. Mitigation: preserve original severity/status and show accepted markers in every output.
- Risk: confusing accepted vs informational. Mitigation: separate flags and docs.
- Rollback point: revert code/docs/tests from this task; no data migration is involved.
