# Feedback Eval Suite Launcher

## Goal

Let admins run Retrieval Quality promoted eval drafts from the browser without copying CLI commands or manually editing suite definitions.

## Requirements

- Eval launcher must include safe feedback draft suites exported under the project storage-adjacent `eval_drafts/` directory.
- Draft discovery must be bounded to the configured storage data directory's sibling `eval_drafts/` root.
- Draft suites must be project/local runtime files; no arbitrary user-provided suite paths may be launched.
- Discovered draft suites must show enough metadata for admins to recognize them: suite id, name, description, suite path, docs/reuse mode, case count, and modified time.
- Browser-launched feedback draft evals must use `reuse_built_kb=True`, matching the existing Retrieval Quality export command, because drafts are authored from the currently built KB.
- Existing checked-in `coffee_smoke` launch behavior must remain working.
- Existing CLI eval and Retrieval Quality export behavior must remain compatible.

## Acceptance Criteria

- [ ] `GET /eval/suites` returns checked-in suites plus valid feedback draft suites from `eval_drafts/` when present.
- [ ] Feedback draft suite ids are stable and can be sent to `POST /eval/runs`.
- [ ] `POST /eval/runs` can launch a discovered feedback draft suite with `reuse_built_kb=True` and writes a report under `.tmp/eval/browser-runs/`.
- [ ] Draft discovery ignores malformed/non-JSONL files without breaking the suite list.
- [ ] Eval Report page displays draft metadata in the suite selector/status panel.
- [ ] Retrieval Quality export summary links users to the Eval Report launcher after exporting.
- [ ] Unit and browser tests cover discovering/exporting/running a feedback draft from user-facing flows.
