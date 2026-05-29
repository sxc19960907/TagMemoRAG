# Q&A empty KB onboarding

## Goal

Improve the user-facing Q&A page when the active knowledge base has no searchable content, so first-time users understand what is missing and can upload, index, and ask from the same page.

## Requirements

- Empty KB state must clearly explain why Q&A is not ready yet.
- Empty KB state must present concrete next steps: choose a manual, index it, then ask.
- Source panel must explain that sources appear after indexing and asking.
- Upload panel should be visually called out while the KB is empty.
- After upload/index succeeds, the page should return to normal ask-ready behavior.
- Existing first-run upload browser test should cover the flow.

## Acceptance Criteria

- [x] Empty Q&A page shows first-run guidance with actionable next steps.
- [x] Empty Q&A page highlights the upload panel.
- [x] Empty Q&A source panel explains when sources will appear.
- [x] Upload/index from Q&A transitions the page to ask-ready state.
- [x] Browser test coverage passes.

## Verification

- `uv run pytest tests/unit/test_manual_library_ui.py tests/unit/test_public_site.py tests/unit/test_documentation_handoffs.py -q`
- `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_manual_rebuild_then_qa_user_flow -q -s`
- `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py`
