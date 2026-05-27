# Implementation Plan

## Checklist

- [x] Refresh pre-development context and load relevant specs.
- [x] Add Q&A page intake markup.
- [x] Add Q&A intake state/actions in `qa_page.js`.
- [x] Add CSS for the intake panel without destabilizing current desktop/mobile Q&A layout.
- [x] Add English/Chinese i18n strings.
- [x] Add/extend unit tests for template/static contracts.
- [x] Add browser integration for QA-first upload -> rebuild -> ask.
- [x] Run focused quality gates:
  - `python3 -m py_compile tests/unit/test_manual_library_ui.py tests/integration/test_browser_admin_ui.py`
  - `node --check src/tagmemorag/web/static/qa_page.js`
  - `uv run pytest tests/unit/test_manual_library_ui.py -q`
  - `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py -q`
  - `uv run python -m tagmemorag readiness browser-qa`
  - `git diff --check`

## Risk Notes

- `qa_page.js` is already large; keep new intake helpers grouped and avoid touching answer rendering unless necessary.
- Manual upload requires multipart form data and no JSON content type.
- Rebuild may return either a task or queued job depending on config.
- Browser tests are opt-in and start real local servers; keep the new flow deterministic with a text manual fixture.

## Rollback

Remove the intake card and associated JS/CSS/i18n/test additions. Existing Q&A and admin Manual Library routes should remain unchanged because this task reuses existing backend APIs.
