# Production Pilot Verification v2 — Design

## Scope

Integrate the existing offline answer-quality diagnostics into the pilot report
pipeline. Reuse `tagmemorag.eval.answer_quality`; do not create a second answer
judge or live-provider call path.

## Current Pilot Flow

`run_production_pilot` stages:

1. `config_validate`
2. `provider_probe`
3. `readiness_smoke`
4. `eval`
5. optional `eval_reauthoring_diagnosis`

`scripts/production_verify.py` calls `run_production_pilot` and reports the
pilot stage aggregate.

## Proposed Pilot Flow

Default stages:

1. `config_validate`
2. `provider_probe`
3. `readiness_smoke`
4. `answer_quality`
5. `eval`
6. optional `eval_reauthoring_diagnosis`

The answer-quality stage calls `run_answer_quality_diagnostics(suite_path)`.
It maps `report.summary.passed` to `passed` or `failed`.

## Stage Detail Contract

The `answer_quality` stage detail includes:

- `suite`: basename only;
- `schema_version`;
- `cases`;
- `passed`;
- `failed`;
- `failures`: bounded list of failing case ids and failure strings.

It must not include fixture context text, generated answer text, raw provider
responses, secrets, or stack traces.

## CLI Contract

`python -m tagmemorag pilot run` adds:

- `--answer-quality-suite`, default
  `tests/fixtures/answer_quality/basic.jsonl`;
- `--skip-answer-quality`, default false.

`scripts/production_verify.py` adds the same options and forwards them to
`run_production_pilot`.

## Compatibility

- Default pilot reports gain one extra stage. This is a deliberate v2 gate.
- Existing retrieval eval behavior and thresholds are unchanged.
- Report schema version can remain `production_pilot.v1` because stage lists
  are already extensible and no existing field changes shape.

## Tests

- Update default pilot test to expect the new stage.
- Add skip-stage test.
- Add override-suite test using a temporary passing suite.
- Assert serialization omits raw fixture answer/context text.
- Update `scripts/production_verify.py` tests to assert forwarding and default
  stage summary behavior.
