# Feedback Triage Workflow Hardening Implementation Plan

## Steps

1. Start the Trellis task and preserve current parent task linkage.
2. Add the triage decision block to the Retrieval Quality template.
3. Extend `retrieval_quality.js` with a derived triage decision helper, renderer, and `Mark Triaged` quick action.
4. Add CSS for a compact operations decision block.
5. Add missing i18n strings for the new labels/guidance.
6. Update focused shell/static and browser integration assertions.
7. Update the trial operator handoff documentation with the clearer route.

## Validation

- `node --check src/tagmemorag/web/static/retrieval_quality.js`
- `python3 -m py_compile tests/unit/test_manual_library_ui.py tests/integration/test_browser_admin_ui.py tests/unit/test_retrieval_feedback_api.py`
- `uv run pytest tests/unit/test_manual_library_ui.py tests/unit/test_retrieval_feedback_api.py -q`
- `uv run pytest tests/integration/test_browser_admin_ui.py -q`
- `uv run python -m tagmemorag readiness browser-qa`
- `git diff --check`
