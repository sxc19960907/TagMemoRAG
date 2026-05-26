# Eval Run Browser Launcher Implementation Plan

1. Read backend and cross-layer Trellis specs.
2. Implement `api_eval_runs.py` with suite definitions, job registry, background runner, and bounded serialization.
3. Wire FastAPI routes in `api.py` and add a small request model if needed.
4. Add Eval Report launch panel in template, JS, CSS, and i18n strings.
5. Add unit tests for suite list, route shell/static wiring, invalid launch, successful job polling, and failed/duplicate behavior where practical.
6. Extend browser smoke to launch the coffee smoke eval and open the generated report.
7. Validate:
   - JS syntax checks
   - focused unit tests
   - eval CLI regression tests
   - browser integration test
   - `git diff --check`
8. Commit implementation, commit task record, archive/journal, commit archive, push.

## Rollback

Remove `/eval/suites`, `/eval/runs`, `api_eval_runs.py`, and the launch panel while keeping report discovery/viewing intact.
