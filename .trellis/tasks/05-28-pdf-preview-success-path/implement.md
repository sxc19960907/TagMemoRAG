# Implementation plan

- [x] Start Trellis task and load backend/frontend specs.
- [x] Inspect current source-preview diagnostics, QA source rendering, `/assets` route, and browser tests.
- [x] Check local PyMuPDF availability and identify whether a real happy-path browser validation can run.
- [x] Add or refine config guidance in admin diagnostics/readiness UI.
- [x] Add success-path tests that are deterministic and skip cleanly when PyMuPDF is missing.
- [x] Run focused tests and browser validation.
- [x] Run broader stable gates, update specs if the contract changes, commit, and archive.

## Validation

- `uv run pytest tests/unit/test_document_assets.py tests/unit/test_retrieval.py tests/unit/test_manual_library_ui.py tests/unit/test_api.py -q`
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_multiformat_manuals_then_qa_user_flow -q`
- Add/run any new targeted browser success-path test.
- `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py`
- `uv run python scripts/run_eval_ci.py`
