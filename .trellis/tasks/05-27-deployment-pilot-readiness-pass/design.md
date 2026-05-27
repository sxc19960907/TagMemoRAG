# Deployment Pilot Readiness Pass Design

## Scope

This task extends the existing local pilot report. It does not change deployment infrastructure, provider probes, eval thresholds, browser UI behavior, or GitHub push policy.

## CLI Contract

`pilot run` gains:

- `--include-browser-qa`: run the focused browser QA readiness gate and include it in the pilot report.
- `--browser-qa-full`: when combined with `--include-browser-qa`, run the full browser UI readiness suite.

The default pilot command remains unchanged.

## Report Stage

Add a `browser_qa_readiness` pilot stage after backend readiness smoke and before answer-quality/eval stages. The stage detail should include:

- browser readiness mode: `focused` or `full`
- target pytest selection from the readiness report
- command list from the readiness report
- duration seconds when present
- return code when present

The pilot stage status maps as:

- `passed` -> `passed`
- `failed` -> `failed`
- `error` -> `failed`

The stage error should include a safe type/reason only; raw browser output should remain inside the browser readiness report object, not expanded into any new sensitive fields.

## Compatibility

Existing callers of `run_production_pilot` and `pilot run` keep current behavior because browser readiness is opt-in.

## Rollback

Remove the new CLI flags, new `run_production_pilot` arguments, browser stage helper, tests, and docs. No persisted data or migration is involved.
