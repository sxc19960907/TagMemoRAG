# Eval Report Discovery Implementation Plan

1. Add task context manifests for backend spec/check context.
2. Implement backend discovery helpers and `/eval/reports` route.
3. Add Eval Report template, CSS, and JS recent-report UI.
4. Add unit tests for route shell, static asset, discovery metadata, malformed handling, and bounded discovery.
5. Extend browser admin UI smoke to open the page without `report_path`, discover a fixture report under `.tmp`, click it, and verify it loads.
6. Run validation:
   - `node --check src/tagmemorag/web/static/eval_report.js`
   - focused unit tests
   - browser integration test with `TAGMEMORAG_RUN_BROWSER_UI=1`
   - `git diff --check`
7. Commit implementation, commit Trellis task record, archive/journal, commit archive, and push.

## Rollback

If discovery causes unsafe path exposure or unstable tests, keep the existing report viewer and remove only `/eval/reports` plus the recent-report UI.
