# Feedback Eval Suite Launcher Implementation Plan

1. Update `api_eval_runs.py` suite model and registry to support static + discovered suites.
2. Implement bounded feedback draft discovery from `eval_drafts/` with case counting and stable ids.
3. Update `/eval/suites` and `/eval/runs` wiring to pass active settings.
4. Update Eval Report UI to display draft metadata and reuse/build mode.
5. Add Retrieval Quality export summary link to Eval Report launcher.
6. Add unit tests for draft discovery, invalid/malformed skip, and launching a discovered draft using a prebuilt KB.
7. Extend browser smoke so Retrieval Quality export can be followed by Eval Report suite discovery/run.
8. Run focused unit, e2e eval, browser, JS, py_compile, and diff checks.
9. Commit implementation, task record, archive/journal, push.

## Rollback

Revert discovered-suite changes while preserving the static `coffee_smoke` launcher and report viewer.
