# QA Browser Regression Smoke Implementation Plan

1. Read Trellis specs before editing.
2. Inspect existing QA browser helpers and choose the smallest stable assertion points.
3. Update `tests/integration/test_browser_admin_ui.py` to assert:
   - first-screen flow guide and empty-state copy;
   - loading progress card/source placeholder during submit;
   - successful answer source metadata and follow-up explanatory copy;
   - feedback controls remain available;
   - recovery card/readiness link in not-ready state.
4. Run syntax/import check for the integration test.
5. Run focused unit tests:
   - `uv run pytest tests/unit/test_manual_library_ui.py tests/unit/test_answer_api.py -q`
6. Run targeted browser test with:
   - `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::<test_name> -q`
7. Run `git diff --check`.
8. Commit implementation, archive task, record journal, and push.

## Risk Notes

- Browser assertions should be meaningful but not overfit exact layout geometry.
- Loading state can be fast; use a lightweight helper that checks it immediately after click but does not make the test flaky if the answer completes quickly.
- Keep tests opt-in and local.
