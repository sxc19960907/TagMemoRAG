# Implementation Plan

1. Add a shared auth generation helper and update the CLI to use it.
2. Add the Pydantic request model and `POST /admin/people/access-keys/generate` route.
3. Extend the People & Access page template, JS, and CSS with the generation form/result.
4. Add focused tests for helper/CLI parity, API generation, auth guard, and static UI content.
5. Run focused Python/JS checks and browser smoke verification.

## Validation

- `.venv/bin/python -m pytest tests/unit/test_manual_library_ui.py tests/unit/test_auth.py tests/unit/test_cli.py`
- `node --check src/tagmemorag/web/static/people_admin.js`
- `.venv/bin/python -m compileall -q src/tagmemorag/api.py src/tagmemorag/auth/keygen.py`
- `git diff --check`

## Rollback

This change is additive except for the CLI helper refactor. Reverting the helper, endpoint, and UI additions restores read-only People & Access behavior.
