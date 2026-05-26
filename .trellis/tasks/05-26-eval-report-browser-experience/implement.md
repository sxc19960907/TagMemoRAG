# Implementation Plan: Eval report browser experience

1. Planning and guidelines
   - Fill PRD/design/implement.
   - Read backend specs and cross-layer guide before edits.
   - Start the Trellis task.

2. Backend report summary
   - Add a small `api_eval_report.py` module for loading and summarizing eval report JSON.
   - Return structured `ServiceError` failures for missing path, missing file, invalid JSON, and malformed report payload.
   - Wire `GET /eval/report` behind `require_scope("admin")`.

3. Browser shell and UI
   - Add `/admin/eval-report` template route.
   - Add `eval_report.html` and `eval_report.js`.
   - Extend shared CSS with report-viewer classes.
   - Add report links from Retrieval Quality promotion summary when `summary.report_path` exists.
   - Add i18n entries for new user-visible labels.

4. Tests
   - Unit tests for route shell and static asset.
   - Unit tests for valid/missing/malformed report API behavior.
   - Browser/static workflow check for report viewer rendering.
   - Existing Retrieval Quality tests updated for the new link.

5. Validation
   - `node --check src/tagmemorag/web/static/eval_report.js`
   - `node --check src/tagmemorag/web/static/retrieval_quality.js`
   - `node --check src/tagmemorag/web/static/i18n.js`
   - Focused pytest for UI/API eval report tests.
   - Relevant browser UI pytest if feasible.
   - `git diff --check`

6. Finish
   - Run Trellis quality check.
   - Commit implementation.
   - Archive task and update journal in a separate closure commit.
