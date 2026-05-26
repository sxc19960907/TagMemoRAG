# Eval Report Discovery

## Goal

Make the browser eval-report workflow usable without requiring an administrator to remember or paste a local JSON report path. The page should discover recent eval report files from bounded project output locations and let the user load one directly.

## Requirements

- Add an admin-only, read-only API that lists recent eval report candidates from safe project-local output directories.
- Discovery must be bounded to known output roots and must not expose arbitrary filesystem traversal.
- The existing `/eval/report?path=...` report loading behavior must remain compatible.
- The Eval Report page must show recent report candidates when opened without a `report_path`.
- Selecting a candidate should populate the path field, load the report, and preserve the current KB navigation links.
- Empty states must be useful when no reports are discovered.
- Tests must create their own report fixtures instead of depending on developer `.tmp/` contents.

## Acceptance Criteria

- [ ] `GET /eval/reports` returns a structured list of recent report candidates with path, display name, modified timestamp, size, and lightweight summary metadata when available.
- [ ] Discovery is limited to project-local `.tmp/` reports and default readiness report paths, with bounded recursion and result count.
- [ ] Malformed JSON files are skipped or marked without breaking the list endpoint.
- [ ] `/admin/eval-report` includes a recent reports panel and still works with explicit `report_path` auto-load.
- [ ] Browser smoke can open the Eval Report page without `report_path`, see a discovered candidate, click it, and inspect loaded cases.
- [ ] Unit and browser tests pass, plus JS syntax checks and `git diff --check`.
