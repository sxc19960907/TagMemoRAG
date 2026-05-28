# QA Source Preview and Verification Implementation Plan

## Checklist

- [x] Read Trellis backend/frontend-relevant specs before editing.
- [x] Inspect current `/assets` route, retrieval asset descriptors, QA source-card rendering, and browser helpers.
- [x] Sanitize safe asset preview descriptors in QA session history.
- [x] Render source verification controls/fallback state in QA source cards.
- [x] Add i18n strings and CSS for the compact verification row.
- [x] Add/update static UI tests for source verification controls and no debug leakage.
- [x] Extend browser regression to exercise citation focus plus source verification action/fallback and history restore.
- [x] Run focused unit/UI tests and relevant browser flows.
- [x] Run CI-equivalent unit/e2e and eval gates.
- [x] Update task acceptance, spec notes if needed, commit, archive, and journal.

## Verification Results

- Focused unit/UI: 66 passed.
- Browser QA regression subset: 4 passed.
- CI unit/e2e gate: 1282 passed.
- Eval gate: all 8 eval suites passed.

## Validation Commands

- `uv run pytest tests/unit/test_manual_library_ui.py tests/unit/test_retrieval.py -q`
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_multiformat_manuals_then_qa_user_flow -q`
- `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py`
- `uv run python scripts/run_eval_ci.py`

## Risk Points

- Do not expose storage keys, blob keys, checksums, or local absolute paths.
- Browser tests should verify behavior/classes and visible user copy without depending on incidental asset ids.
- Preview links must stay KB/auth-bound through existing `/assets` route.
