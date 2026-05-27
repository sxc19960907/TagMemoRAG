# Upload Rebuild Recovery Black Box Review Implementation Plan

## Steps

1. Start the child task after reading specs.
2. Inspect existing Manual Library upload/rebuild/diagnostics UI and tests.
3. Add the smallest browser-visible recovery guidance needed for failed rebuild states.
4. Extend unit/static assertions for new UI copy or functions.
5. Extend focused browser tests for invalid upload, pending rebuild, and recovery guidance.
6. Update trial operator handoff if the recovery route wording changes.

## Validation

- `node --check src/tagmemorag/web/static/manual_library.js`
- `python3 -m py_compile tests/unit/test_manual_library_ui.py tests/integration/test_browser_admin_ui.py`
- `uv run pytest tests/unit/test_manual_library_ui.py -q`
- `uv run python -m tagmemorag readiness browser-qa`
- `uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_rag_failure_states -q`
- `git diff --check`
