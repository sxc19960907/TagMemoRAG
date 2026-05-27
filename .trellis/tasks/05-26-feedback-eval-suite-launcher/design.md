# Feedback Eval Suite Launcher Design

## Scope

This task extends the existing browser eval launcher with discovered feedback draft suites. It does not add arbitrary upload, case editing, deletion, scheduling, or persistent job history.

## Backend

Extend `api_eval_runs.py`:

- `BrowserEvalSuite` gains:
  - `kind`: `fixture` or `feedback_draft`
  - `reuse_built_kb`: bool
  - `case_count`: int
  - `modified_at`: float | None
- Static checked-in suites remain in a constant.
- `discover_feedback_draft_suites(settings, project_root)` scans:
  - `Path(settings.storage.data_dir).resolve().parent / "eval_drafts"`
  - bounded recursion depth and max files
  - JSONL files only
- Each candidate is validated by reading JSONL rows as JSON objects and requiring at least one row with `id`, `query`, `kb_name`, and `relevant` list.
- Suite id format: `feedback_draft:<safe relative path without suffix>` encoded with a URL-safe digest suffix to avoid collisions.
- Feedback draft runs call `run_eval(..., reuse_built_kb=True, docs_path=None)`.
- Static fixture runs keep existing docs build behavior.

`GET /eval/suites` and `POST /eval/runs` must pass current `settings` into the registry so discovered suites reflect the active config.

## Frontend

`eval_report.js` already renders suite options from API metadata. Enhance the idle panel to show description, case count, suite kind, and reuse/build mode.

`retrieval_quality.js` export summary already renders `summary.report_path` and command. Add an Eval Report link using `summary.suite_path` so the admin can jump to the launcher/report page after export.

## Safety

- No arbitrary paths accepted from browser launch requests.
- Discovery root is derived from config and bounded.
- Malformed draft files are skipped from suite list rather than exposed as launchable tasks.
- Existing report content remains bounded by eval report contracts.
