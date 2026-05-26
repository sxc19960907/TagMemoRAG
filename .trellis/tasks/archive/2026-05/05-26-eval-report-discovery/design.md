# Eval Report Discovery Design

## Scope

This task extends the existing Eval Report viewer with report discovery. It does not run eval jobs in the browser and does not change the CLI report schema.

## Backend

`src/tagmemorag/api_eval_report.py` owns the feature because it already owns report loading and summarization. Add:

- `list_eval_report_candidates(project_root=Path.cwd(), limit=20)` returning schema `eval_report_list.v1`.
- bounded discovery roots:
  - `<project_root>/.tmp`
  - parent directories from `release_readiness.DEFAULT_REPORT_PATHS` when they are project-local
- safe path handling through `Path.resolve()` plus a project-root containment check.
- candidate metadata from file stats plus optional lightweight JSON fields: suite, kb_names, summary.passed, summary.cases, summary failed count when present.

The FastAPI route lives next to `/eval/report`:

- `GET /eval/reports?limit=20`
- admin scope and rate limiting match `/eval/report`.

Known malformed report-shaped JSON files should not fail the list. Candidate entries can include `valid=false` and an error string, while unreadable/non-JSON files can be skipped if they are not likely eval reports.

## Frontend

`eval_report.html` gets a recent reports section near the top of the main content. `eval_report.js` adds:

- `loadRecentReports()` after i18n initialization.
- `renderRecentReports()` with compact buttons/cards.
- click handler that writes the report path input and calls `loadReport()`.
- explicit `report_path` still auto-loads on page open.

The UI should be operational and quiet: a list of recent reports, status chips, timestamp/path, and a direct load action.

## Compatibility and Safety

- Existing report viewer API remains unchanged.
- No arbitrary discovery root query parameter is accepted.
- The full path is already accepted by the existing admin-only loader; discovery only reduces friction within bounded project roots.
