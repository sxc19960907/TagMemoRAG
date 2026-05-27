# Implementation Plan

## Checklist

- [x] Add first-run guidance rendering to the QA workspace.
- [x] Detect empty/not-ready KB from `/kb` and initial placeholder state.
- [x] Generate uploaded-manual suggestions after successful index.
- [x] Add rebuild-failure recovery links for QA-page upload.
- [x] Add i18n strings.
- [x] Extend unit/static and browser integration tests.
- [x] Run focused gates:
  - `python3 -m py_compile tests/unit/test_manual_library_ui.py tests/integration/test_browser_admin_ui.py`
  - `node --check src/tagmemorag/web/static/qa_page.js`
  - `uv run pytest tests/unit/test_manual_library_ui.py -q`
  - `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_qa_page_upload_rebuild_then_answer tests/integration/test_browser_admin_ui.py::test_browser_rag_failure_states_are_user_visible -q`
  - `uv run python -m tagmemorag readiness browser-qa`
  - `git diff --check`

## Verification Notes

- `python3 -m py_compile tests/unit/test_manual_library_ui.py tests/integration/test_browser_admin_ui.py` passed.
- `node --check src/tagmemorag/web/static/qa_page.js` passed.
- `uv run pytest tests/unit/test_manual_library_ui.py -q` passed with 39 tests.
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_qa_page_upload_rebuild_then_answer tests/integration/test_browser_admin_ui.py::test_browser_rag_failure_states_are_user_visible -q` passed with 2 tests.
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py -q` passed with 8 tests.
- `uv run python -m tagmemorag readiness browser-qa` passed.
- `git diff --check` passed.

## Spec Update Review

No `.trellis/spec/` update is needed for this task. The implementation is frontend-only and reuses existing QA, manual upload, readiness, and manual-library API/page contracts without adding a new API signature, persistence contract, command, or cross-layer data format.

## Rollback

Remove the frontend-only first-run/suggestion/recovery helpers and related tests. Existing upload and Q&A flows should remain as before.
