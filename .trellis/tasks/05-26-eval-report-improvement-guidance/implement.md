# Implementation Plan: Eval report improvement guidance

1. Read task artifacts and applicable Trellis specs.
2. Start task with `task.py start`.
3. Backend:
   - Add guidance derivation helper(s) to `api_eval_report.py`.
   - Add `guidance`, `primary_issue`, and top-level `guidance_counts`.
   - Keep output bounded and report-only.
4. UI:
   - Render guidance cards in `eval_report.js`.
   - Add CSS and i18n entries.
5. Tests:
   - Add unit assertions for guidance fields and grouped counts.
   - Add cases for no-match, partial-recall, low-rank, negative-hit, and weak matcher.
   - Update browser smoke to assert guidance is visible.
6. Validate:
   - `node --check src/tagmemorag/web/static/eval_report.js`
   - `node --check src/tagmemorag/web/static/i18n.js`
   - `uv run pytest tests/unit/test_manual_library_ui.py tests/e2e/test_eval_cli.py -q`
   - `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_eval_report_viewer -q -s`
   - `git diff --check`
7. Commit implementation, commit task record, archive task, update journal, push.
