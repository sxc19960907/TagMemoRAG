# Implementation Plan

1. Verify local prerequisites without exposing secrets:
   - required env names are set
   - Docker is reachable
   - provider services can be started or reused
2. Run a check-only unified provider verification to catch missing env/S3/Docker setup issues early.
3. Run the full unified live pilot command:
   - config: `examples/config/production-provider-verification.yaml`
   - suite: `tests/fixtures/eval/coffee.jsonl`
   - docs: `tests/fixtures`
   - hashing baseline: `tests/fixtures/eval/baselines/hashing.json`
   - production baseline: `tests/fixtures/eval/baselines/siliconflow.json`
   - informational suites: `cross_kb_negatives.jsonl,fault_codes.jsonl,model_numbers.jsonl,tag_cooccurrence.jsonl`
   - accepted suites: `product_manuals.jsonl,mixed_language.jsonl,tag_rerank_edge.jsonl`
   - outputs under `.tmp/production-provider-verification/live-pilot/`
4. Inspect JSON reports with structured parsing and redact any sensitive traces before documentation.
5. Write a concise sanitized evidence document under `docs/`.
6. Run privacy grep and relevant CLI/unit checks.
7. Archive task, record journal, commit, PR, and merge if checks are clean.

## Validation Commands

```bash
uv run python -m tagmemorag production-provider verify --level pilot ...
uv run pytest tests/unit/test_production_provider_verify.py tests/unit/test_cli_production_provider_verify.py tests/unit/test_production_provider_smoke.py tests/unit/test_run_production_provider_smoke.py
python3 -m py_compile src/tagmemorag/production_provider_verify.py src/tagmemorag/production_pilot.py
rg -n "sk-[A-Za-z0-9]{8,}|Authorization: Bearer|raw answer|retrieved snippet|answer text" docs .trellis/tasks/archive/2026-05/05-21-live-pilot-provider-verification
```

## Risk / Rollback

- Live provider calls can fail due external service/network/model behavior; capture stage failure and do not hide it.
- Docker services may already be running; the verify command can return `warning` when downstream checks prove services are usable.
- Runtime `.tmp/` reports are not committed; only sanitized summaries are committed.
