# Production Pilot Verification v2 — Implementation Plan

## Steps

1. Update `production_pilot.py`:
   - add default answer-quality suite constant;
   - add `answer_quality_suite_path` and `skip_answer_quality` parameters;
   - add `_answer_quality_stage` helper.
2. Update CLI:
   - add `pilot run --answer-quality-suite`;
   - add `pilot run --skip-answer-quality`;
   - pass both into `run_production_pilot`.
3. Update `scripts/production_verify.py`:
   - add matching function parameters and CLI flags;
   - forward settings to `run_production_pilot`.
4. Update docs/runbook to mention the v2 answer-quality stage.
5. Add/update tests.

## Validation Commands

```bash
uv run pytest tests/unit/test_production_pilot.py tests/unit/test_production_verify.py
uv run python -m tagmemorag pilot run \
  --config examples/config/local-hashing-npz.yaml \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --workdir .tmp/pilot-v2 \
  --output .tmp/pilot-v2/report.json
git diff --check
uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py
```

## Exit Criteria

- [x] Default `pilot run` includes `answer_quality` between readiness and
      retrieval eval.
- [x] `--skip-answer-quality` removes the stage.
- [x] `--answer-quality-suite <path>` overrides the default suite.
- [x] Pilot JSON/Markdown reports stay sanitized and do not include raw fixture
      answer/context text.
- [x] `scripts/production_verify.py` exposes matching answer-quality options
      and passes them to `run_production_pilot`.
- [x] Focused production pilot and verification tests pass.
