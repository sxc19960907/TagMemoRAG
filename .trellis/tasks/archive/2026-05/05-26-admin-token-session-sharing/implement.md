# Implementation Plan

1. Add `admin_token.js` helper.
2. Convert page scripts that are already modules to import the helper directly.
3. Convert non-module admin scripts to module script tags where needed, then import the helper.
4. Update static asset tests to assert shared token wiring.
5. Run focused tests and JS syntax checks.

## Validation

- `.venv/bin/python -m pytest tests/unit/test_manual_library_ui.py -q`
- `node --check src/tagmemorag/web/static/admin_token.js src/tagmemorag/web/static/manual_library.js src/tagmemorag/web/static/rag_workbench.js src/tagmemorag/web/static/people_admin.js src/tagmemorag/web/static/retrieval_quality.js src/tagmemorag/web/static/qa_page.js`
- `git diff --check`

## Rollback

Revert the helper and page imports/listener changes. Existing per-page token inputs remain in templates.
