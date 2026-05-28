# Browser multiformat document intake validation

## Goal

Make the browser-first RAG intake path trustworthy for common real user documents. A user should be able to upload Markdown/TXT, text-based PDF, scanned PDF with OCR enabled, and DOCX from the Manual Library or QA-facing flow, rebuild/index them, understand format-specific diagnostics, and ask grounded QA without using the command line.

## Confirmed Facts

- Native parsing supports `.md`, `.txt`, and `.pdf`.
- Manual Library and QA upload inputs already allow `.md`, `.txt`, `.pdf`, and `.docx`.
- Managed DOCX upload is implemented by converting readable OpenXML text into Markdown while preserving `source_format=docx` and the original path in `remote_id`.
- HTML support exists only when `parser.provider=langchain`; it is not part of the default browser upload contract.
- Browser integration currently covers Markdown upload/QA and scanned PDF OCR upload/QA, but not a combined TXT + text PDF + DOCX browser user flow.

## Requirements

- Cover the default browser-supported document set: `.md`, `.txt`, text-based `.pdf`, scanned `.pdf` when OCR is enabled, and `.docx`.
- Verify the user-facing Manual Library upload accepts TXT, text PDF, and DOCX files, triggers rebuild, marks records searchable, and preserves helpful source metadata.
- Verify DOCX upload is visible to the user as an accepted document while the indexed source remains the converted Markdown file with original DOCX provenance retained.
- Verify QA can answer from indexed evidence across TXT, text PDF, DOCX-converted Markdown, and scanned-PDF OCR content.
- Verify diagnostics remain safe and understandable: PDF quality/OCR status is exposed as counts/status, not raw extracted document text.
- Keep default OCR behavior off unless a test/config explicitly enables it.
- Avoid adding production dependencies for sample generation; test fixtures should use existing project dependencies and standard library helpers.
- Do not include HTML in the default acceptance path unless a separate langchain-provider task is created.

## Acceptance Criteria

- [x] A Trellis task documents supported browser intake formats and explicitly excludes HTML/default-off extras from this slice.
- [x] Browser/static smoke confirms Manual Library and QA upload controls advertise `.md`, `.txt`, `.pdf`, and `.docx`.
- [x] A browser integration flow uploads TXT, text PDF, and DOCX through the Manual Library upload dialog and rebuilds through the same public endpoints used by the UI.
- [x] Uploaded TXT, PDF, and DOCX records become searchable with non-zero chunk counts and no pending rebuild state.
- [x] DOCX conversion stores/indexes a Markdown source while retaining `source_format=docx` and original DOCX path provenance.
- [x] QA answers or cited sources prove retrieval from TXT, text PDF, DOCX, and the already-covered scanned PDF OCR path.
- [x] Diagnostics expose format/OCR/PDF quality status without leaking raw extracted or OCR text.
- [x] Focused browser integration, unit/UI regression, and CI-equivalent tests pass.

## Verification Notes

- Added `test_browser_upload_multiformat_manuals_then_qa_user_flow`, covering TXT, text PDF, and DOCX uploads through the Manual Library dialog, rebuild readiness, provenance checks, diagnostics safety, and QA evidence from each uploaded format.
- Preserved the existing scanned PDF OCR browser smoke as the image-only PDF acceptance proof.
- Fixed an incremental rebuild diagnostics gap: incremental rebuilds now carry forward old OCR/PDF quality summaries and add summaries for newly parsed dirty documents.
- Added a unit regression for preserving `pdf_quality` after incremental rebuilds.
- Commands run:
  - `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_multiformat_manuals_then_qa_user_flow -q`
  - `TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_manual_rebuild_then_qa_user_flow tests/integration/test_browser_admin_ui.py::test_browser_upload_multiformat_manuals_then_qa_user_flow tests/integration/test_browser_admin_ui.py::test_browser_upload_scanned_pdf_rebuilds_with_real_ocr_then_qa -q`
  - `uv run pytest tests/unit/test_manual_library.py::test_incremental_rebuild_preserves_pdf_quality_summary -q`
  - `uv run pytest tests/unit/test_manual_library.py tests/unit/test_manual_bulk_import.py tests/unit/test_manual_library_ui.py tests/unit/test_langchain_ingestion.py -q`
  - `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py`
  - `uv run python scripts/run_eval_ci.py`

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
