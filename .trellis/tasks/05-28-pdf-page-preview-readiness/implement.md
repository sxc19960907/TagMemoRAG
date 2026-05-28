# Implementation plan

## Steps

- [x] Start the Trellis task and load backend/frontend specs.
- [x] Add a backend helper that computes sanitized source preview readiness from settings, graph metadata, and asset manifest inventory.
- [x] Add source preview diagnostics and recommendations to Manual Library diagnostics.
- [x] Add source preview detail and recommendation to RAG Readiness.
- [x] Improve QA source fallback copy while preserving safe asset URL filtering.
- [x] Add focused tests for diagnostics, readiness, static QA behavior, and browser fallback.
- [x] Run focused tests, then broader stable gates.
- [x] Update task acceptance checkboxes and archive when quality gates pass.

## Validation

- `uv run pytest tests/unit/test_document_assets.py tests/unit/test_manual_library_ui.py tests/unit/test_api.py -q`
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_multiformat_manuals_then_qa_user_flow -q`
- `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py`
- `uv run python scripts/run_eval_ci.py`

## Rollback points

The backend diagnostics are additive. If a frontend issue appears, keep the diagnostics payload and revert only rendering/copy changes. If diagnostics become noisy, remove the readiness recommendation while retaining the sanitized status for future UI use.
