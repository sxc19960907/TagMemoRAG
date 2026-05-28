# Scanned PDF browser upload OCR flow

## Goal

Verify and harden the real browser user flow for uploading a scanned PDF, rebuilding with OCR, seeing diagnostics, and asking QA from the indexed OCR content.

## Requirements

- Use the generated scanned PDF sample as a realistic browser-uploaded document, not a direct `build_kb` shortcut.
- Verify Manual Library upload accepts the scanned PDF, stores it as a managed manual, and marks rebuild required.
- Verify rebuild with `ocr.provider=tesseract_cli` uses real local OCR and indexes searchable OCR chunks.
- Verify Manual Library diagnostics shows OCR/PDF quality status after rebuild.
- Verify QA can answer a weak-steam question from the uploaded scanned PDF.
- If browser automation cannot type/select files due environment limitations, keep a black-box HTTP/API fallback that exercises the same browser routes and public endpoints.
- Preserve default-off OCR behavior and avoid leaking OCR text in diagnostics.

## Acceptance Criteria

- [x] Browser route/static smoke proves Manual Library and QA pages expose the normal user workflow for the target KB.
- [x] Uploading the scanned PDF through the Manual Library upload endpoint creates a managed manual and pending rebuild state.
- [x] Rebuild succeeds with real `tesseract_cli` OCR and records OCR/PDF quality metadata.
- [x] Diagnostics reports OCR enabled, `tesseract_cli`, OCR-created chunks/pages, and no missing OCR commands.
- [x] QA answer or retrieval returns evidence from the uploaded scanned PDF containing `STEAM-042`, `steam nozzle`, or weak-steam guidance.
- [x] Any missing UX gap discovered in this flow is fixed with focused tests.
- [x] Focused automated tests or documented black-box smoke commands pass.

## Verification Notes

- Added `test_browser_upload_scanned_pdf_rebuilds_with_real_ocr_then_qa`, a browser integration smoke that uploads `.tmp/ocr-samples/scanned-coffee-manual.pdf` through Manual Library, waits for rebuild, checks OCR diagnostics via the public diagnostics endpoint, and asks QA from the indexed OCR content.
- The OCR browser smoke is opt-in like the rest of `tests/integration/test_browser_admin_ui.py` and skips cleanly when `tesseract`, `pdftoppm`, or the generated scanned-PDF sample is unavailable.
- Verified diagnostics expose OCR/PDF-quality counts and command availability without exposing raw OCR text.
- Commands run:
  - `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_scanned_pdf_rebuilds_with_real_ocr_then_qa -q`
  - `uv run pytest tests/unit/test_manual_library_api.py tests/unit/test_manual_library_ui.py tests/unit/test_ocr_provider.py tests/unit/test_ocr_config.py -q`
  - `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_manual_rebuild_then_qa_user_flow tests/integration/test_browser_admin_ui.py::test_browser_qa_page_upload_rebuild_then_answer -q`
  - `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py`
  - `uv run python scripts/run_eval_ci.py`

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
