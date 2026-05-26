# Eval report browser experience

## Goal

Make the feedback-to-eval loop understandable from the browser. After an operator exports feedback into an eval draft and runs the suggested `tagmemorag eval run --output ...` command, they should be able to open a browser page, load the generated JSON report, understand whether retrieval quality passed, and identify which cases need action.

This closes the current product gap between "the UI tells me what command to run" and "I can interpret the resulting eval report without reading raw JSON."

## Confirmed Facts

- `tagmemorag eval run --output <path>` writes an `EvalReport` JSON object with `summary`, `cases`, `expected`, `actual_top_k`, `failures`, thresholds, and config snapshot fields.
- Retrieval Quality promotion already exposes `summary.report_path` and `summary.next_command`.
- The existing browser admin surfaces use FastAPI templates under `src/tagmemorag/web/templates`, JS modules under `src/tagmemorag/web/static`, shared admin-token handling, and optional i18n.
- Feedback review endpoints require admin scope; report viewing should follow the same admin-only model.
- The browser should not execute eval jobs in this task. Running eval can be long-running and may require docs/config choices; the prior task already exposes the safe command.

## Requirements

- Add a browser page for viewing an existing eval JSON report.
- Add an admin API endpoint that reads a generated eval report from a local path and returns a UI-oriented summary.
- The report view must show suite path, docs path if present, KB names, top K, pass/fail status, aggregate metrics, and run context.
- The report view must show passed/failed/urgent/review/ok counts.
- The report view must list failed/review cases first with query, KB, metrics, failures, expected evidence, actual top results, and matched expected indexes when available.
- Retrieval Quality promotion guidance must link to the report viewer using the suggested `report_path`.
- Empty, missing-file, invalid JSON, and malformed report states must be understandable in the browser.
- The implementation must preserve current CLI report compatibility and must not mutate eval reports.
- The UI must support existing Chinese/English language switching for new visible text where practical.

## Acceptance Criteria

- [ ] `/admin/eval-report?report_path=<path>` serves a browser shell with shared admin token and language controls.
- [ ] `GET /eval/report?path=<path>` requires admin scope and returns a summarized, bounded payload for valid eval reports.
- [ ] Invalid or missing report paths return structured errors rather than server tracebacks.
- [ ] Retrieval Quality promotion cards include an "Open report" action when `summary.report_path` is available.
- [ ] Unit tests cover the route shell, static asset, valid report summary, missing file, and malformed report behavior.
- [ ] Browser/UI tests cover a report viewer smoke path or a focused static/browser workflow if a full eval run is too expensive.
- [ ] Static JS checks and relevant pytest suites pass.

## Out of Scope

- Executing eval jobs from the browser.
- Editing eval suites from the report page.
- Persisting a separate report database.
