# Production verification report command implementation plan

## Checklist

- [x] Implement `scripts/production_verify.py`.
- [x] Add focused unit tests.
- [x] Update `docs/production-environment-verification.md`.
- [x] Run focused tests and local command smoke.
- [x] Run `git diff --check`.
- [ ] Commit, archive, and journal.

## Validation Commands

```bash
uv run python scripts/production_verify.py --format json --output .tmp/production-verification/report.json
uv run python scripts/production_verify.py --format markdown --output .tmp/production-verification/report.md
uv run pytest tests/unit/test_production_verify.py tests/unit/test_production_pilot.py tests/unit/test_config_env.py -q
git diff --check
```

## Results

- `uv run python scripts/production_verify.py --format json --output .tmp/production-verification/report.json` -> passed.
- `uv run python scripts/production_verify.py --format markdown --output .tmp/production-verification/report.md` -> passed.
- `uv run pytest tests/unit/test_production_verify.py tests/unit/test_production_pilot.py tests/unit/test_config_env.py -q` -> 48 passed.
- `git diff --check` -> passed.
