# Implementation Plan

## Checklist

- [x] Capture current docs/UI/test evidence in `research/acceptance.md`.
- [x] Run focused public docs checks:
  - `uv run pytest tests/unit/test_public_site.py tests/unit/test_documentation_handoffs.py -q`
- [x] Run browser first-run QA upload flow:
  - `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_qa_page_upload_rebuild_then_answer -q -s`
- [x] Run browser multiformat upload/Q&A flow:
  - `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_multiformat_manuals_then_qa_user_flow -q -s`
- [x] Check OCR/scanned-PDF prerequisites and run the OCR browser flow when available:
  - `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_scanned_pdf_rebuilds_with_real_ocr_then_qa -q -s`
- [x] Review failures or UX mismatches and implement scoped fixes.
- [x] Re-run affected focused tests.
- [x] Run final quality gate appropriate to touched files.
- [x] Mark PRD acceptance criteria and record verification notes.
- [ ] Commit implementation, archive task, record journal, push, and watch CI.

## Risk Points

- Browser tests are slower and opt-in; do not replace them with command-only checks.
- OCR depends on local `pdftoppm`, `tesseract`, and the generated sample PDF.
- Public docs labels can drift from UI labels. If a mismatch is only documentation text, prefer fixing docs over changing stable UI.
- Avoid committing runtime data under `.tmp/`.

## Success Signal

A new evaluator can follow the documented local browser path and reach a cited Q&A answer over uploaded real documents, with clear source verification and no internal storage details exposed.
