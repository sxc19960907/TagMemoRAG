# Eval Suite History Panel Design

## Backend

`api_eval_runs.list_eval_suites` remains the API boundary for browser-safe suite discovery. It will enrich each suite dict with a `latest_report` field by reusing the bounded report discovery helper in `api_eval_report`.

Matching rules:

- A report matches a suite when the report summary `suite` equals either the suite's resolved path or browser-facing `suite_path`.
- Paths are normalized conservatively as strings; failures to resolve are ignored rather than surfacing as API errors.
- Only valid report candidates are eligible.
- The newest candidate by `modified_at` wins.

The enrichment is additive, so older frontend assumptions remain valid.

## Frontend

The Eval Report page gains a suite history panel below the run launcher. The panel uses the same `state.suites` payload already loaded for the selector.

Actions:

- Select: sets the run-launcher selector and updates suite detail text.
- Run: selects the suite and starts the existing eval run flow.
- Open latest: links to `/admin/eval-report?report_path=...`.
- Load latest: loads the report into the current viewer.

## Safety

- No write operation is added.
- Report discovery stays under existing project-bounded report roots.
- Feedback draft discovery remains under the config-derived `eval_drafts` root and retains existing file/depth bounds.
- No raw report case text is exposed in suite history metadata.

## Compatibility

- `schema_version` remains `eval_suites.v1` because the change is additive and existing consumers can ignore the new field.
- Existing report list and run endpoints are unchanged.
