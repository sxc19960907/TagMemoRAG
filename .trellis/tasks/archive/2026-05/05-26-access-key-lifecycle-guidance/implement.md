# Implementation Plan

1. Extend `people_admin.html` with a lifecycle section in the selected-access detail pane.
2. Update `people_admin.js` to render revoke snippets, rotate plans, and "Use as template" behavior.
3. Add scoped CSS for lifecycle controls and snippets.
4. Update focused UI/static tests.
5. Run JS/Python checks and browser smoke verification.

## Validation

- `.venv/bin/python -m pytest tests/unit/test_manual_library_ui.py tests/unit/test_auth.py tests/unit/test_cli.py -q`
- `node --check src/tagmemorag/web/static/people_admin.js`
- `git diff --check`

## Rollback

This is UI-only. Reverting the template/JS/CSS additions restores the prior People & Access page.
