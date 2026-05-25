# Implementation Plan

1. Add the People & Access route and safe access-summary endpoint in `src/tagmemorag/api.py`.
2. Add `people_admin.html` and `people_admin.js` under the existing web template/static structure.
3. Extend `manual_library.css` with scoped People & Access classes and add a RAG Workbench nav link.
4. Add unit tests for route shell, static asset, safe payload, and admin-scope enforcement.
5. Run focused tests, then archive the task and record the journal after commit.

## Validation

- `python3 -m pytest tests/unit/test_manual_library_ui.py tests/unit/test_auth.py`
- If API auth tests are placed elsewhere, include that focused test file.

## Rollback Points

- The change is additive. Removing the new route/template/static files and workbench link restores the previous admin UI.
