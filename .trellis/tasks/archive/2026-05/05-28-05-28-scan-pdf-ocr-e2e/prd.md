# Scan PDF OCR end-to-end smoke

## Goal

Verify the generated scanned PDF can flow through OCR ingestion, indexing, retrieval, and user-facing QA without regressing default-off OCR behavior.

## Requirements

- Use the generated image-only PDF fixture at `.tmp/ocr-samples/scanned-coffee-manual.pdf` as the real scanned document sample.
- Verify the document has no native extractable PDF text before OCR is enabled.
- Run an OCR-enabled ingestion/indexing path with `ocr.provider=tesseract_cli` when the local system commands are available.
- Confirm OCR output becomes normal searchable RAG content, not a separate command-only artifact.
- Validate retrieval or QA can answer a weak-steam troubleshooting question from the scanned document.
- Preserve default-off OCR behavior and avoid requiring Tesseract/Poppler in normal CI.
- If the local OCR commands are unavailable or OCR quality is insufficient, report the concrete blocker and make the smallest safe improvement needed.

## Acceptance Criteria

- [x] The scanned PDF fixture is confirmed image-only (`extract_text` returns no useful text).
- [x] An OCR-enabled build/index step succeeds or fails with a clear operator-facing prerequisite error.
- [x] OCR/parser metadata records one missing-text page and a created OCR page/chunk when OCR succeeds.
- [x] Search or QA returns evidence containing at least one scanned-document marker such as `STEAM-042`, `steam nozzle`, or weak-steam troubleshooting steps.
- [x] A user-facing QA/browser smoke is performed when the local app can be served.
- [x] Focused automated tests or existing test gates are run for any code changes made.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

## Verification Notes

- `.tmp/ocr-samples/scanned-coffee-manual.pdf` has 1 page and no extractable native text.
- `ocr.provider=tesseract_cli` config validation reports `pdftoppm` available and `tesseract` missing as a warning with `field=ocr.tesseract_command`.
- A temporary `ocrscan` KB built from the real scanned PDF with a fixture OCR provider produced 7 `pdf_ocr:product_manual` chunks.
- Saved KB metadata recorded `pdf_quality.pages_missing_text=1`, `pdf_quality.ocr_pages_created=1`, `ocr.attempted=1`, and `ocr.created=7`.
- CLI search and `/qa/answer` returned scanned-document evidence from `scanned-coffee-manual.pdf`, including weak steam guidance, `steam nozzle`, and `STEAM-042`.
- The QA page loaded at `http://127.0.0.1:8001/qa?kb_name=ocrscan` and displayed `ocrscan · ready · 7 chunks`; browser automation could not type into the field because the in-app browser virtual clipboard was unavailable, so the final answer submission was verified through the same page API (`/qa/answer`).
- Focused tests passed: `uv run pytest tests/unit/test_parser.py::test_parse_pdf_ocr_empty_page_becomes_chunk tests/unit/test_storage_state.py::test_build_kb_includes_ocr_text_for_empty_pdf_pages tests/unit/test_ocr_config.py tests/unit/test_ocr_provider.py -q`.
