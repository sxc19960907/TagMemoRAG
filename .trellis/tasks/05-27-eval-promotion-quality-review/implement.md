# Eval Promotion Quality Review Implementation Plan

## Steps

1. Start the child task after reading specs.
2. Add quality metadata to feedback promotion cases.
3. Render quality level/message/signals in Retrieval Quality promotion cards.
4. Add i18n strings for new quality labels.
5. Update unit and browser/static assertions.
6. Validate, commit, archive, and journal.

## Validation

- `node --check src/tagmemorag/web/static/retrieval_quality.js`
- `python3 -m py_compile tests/unit/test_retrieval_feedback.py tests/unit/test_manual_library_ui.py tests/integration/test_browser_admin_ui.py`
- `uv run pytest tests/unit/test_retrieval_feedback.py tests/unit/test_manual_library_ui.py -q`
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_manual_library_to_qa_user_flow -q`
- `uv run python -m tagmemorag readiness browser-qa`
- `git diff --check`
