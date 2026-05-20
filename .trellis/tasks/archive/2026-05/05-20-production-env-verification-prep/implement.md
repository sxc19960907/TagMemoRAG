# Production environment verification prep implementation plan

## Checklist

- [x] Add `docs/production-environment-verification.md`.
- [x] Link it from `docs/production-deployment-operations.md` and README's deployment docs list.
- [x] Run deterministic docs-adjacent validation commands.
- [x] Run focused tests if docs references touch command contracts.
- [ ] Commit, archive, and journal.

## Validation Commands

```bash
uv run python -m tagmemorag config validate --config examples/config/local-hashing-npz.yaml
uv run python -m tagmemorag readiness smoke
uv run python -m tagmemorag pilot run --config examples/config/local-hashing-npz.yaml --suite tests/fixtures/eval/coffee.jsonl --docs tests/fixtures --hashing-baseline tests/fixtures/eval/baselines/hashing.json --production-baseline tests/fixtures/eval/baselines/siliconflow.json --informational-suites cross_kb_negatives.jsonl,fault_codes.jsonl,model_numbers.jsonl,tag_cooccurrence.jsonl --accepted-suites product_manuals.jsonl,mixed_language.jsonl,tag_rerank_edge.jsonl --workdir .tmp/production-env-verification/pilot --output .tmp/production-env-verification/pilot/report.json
uv run pytest tests/unit/test_production_pilot.py tests/unit/test_provider_probe.py tests/unit/test_config_env.py -q
git diff --check
```

## Results

- `uv run python -m tagmemorag config validate --config examples/config/local-hashing-npz.yaml` -> passed.
- `uv run python -m tagmemorag readiness smoke` -> passed.
- `uv run python -m tagmemorag pilot run ... --output .tmp/production-env-verification/pilot/report.json` -> passed.
- `uv run pytest tests/unit/test_production_pilot.py tests/unit/test_config_env.py tests/unit/test_cli.py -q` -> 69 passed.
- `git diff --check` -> passed.
- Note: bare `python` is not installed in this shell; local verification used the project-standard `uv run python` wrapper.
