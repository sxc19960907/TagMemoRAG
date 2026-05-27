# Auth Role Boundary Trial Review Implementation Plan

## Steps

1. Start the child task after reading specs.
2. Add People & Access boundary guide markup.
3. Add frontend error mapping for People & Access 401/403 responses.
4. Add i18n strings and lightweight CSS.
5. Extend static shell/asset tests and keep existing backend auth tests.
6. Validate, commit, archive, and journal.

## Validation

- `node --check src/tagmemorag/web/static/people_admin.js`
- `python3 -m py_compile tests/unit/test_manual_library_ui.py`
- `uv run pytest tests/unit/test_manual_library_ui.py -q`
- `git diff --check`
