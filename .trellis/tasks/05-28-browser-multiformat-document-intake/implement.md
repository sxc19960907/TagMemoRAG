# Browser Multiformat Document Intake Implementation Plan

## Checklist

- [ ] Read Trellis backend specs before editing.
- [ ] Inspect existing parser/manual-library/browser test helpers.
- [ ] Add reusable test fixture helpers for TXT, DOCX, and text PDF samples using standard library/project dependencies only.
- [ ] Add a browser integration test that uploads TXT, text PDF, and DOCX through Manual Library, waits for rebuild, verifies rows/provenance, and asks QA across the uploaded formats.
- [ ] Add or update unit/UI smoke tests only if a discovered UX or contract gap requires code changes.
- [ ] Run focused browser integration tests:
  - new multiformat browser test
  - existing Markdown upload QA test
  - existing QA-page upload QA test
  - existing scanned PDF OCR browser smoke when local OCR tools/sample are available
- [ ] Run focused unit tests:
  - `tests/unit/test_manual_library.py`
  - `tests/unit/test_manual_bulk_import.py`
  - `tests/unit/test_manual_library_ui.py`
  - `tests/unit/test_langchain_ingestion.py`
- [ ] Run CI-equivalent checks:
  - `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py`
  - `uv run python scripts/run_eval_ci.py`
- [ ] Update PRD acceptance and verification notes.
- [ ] Commit work, archive task, record journal.

## Risk Points

- PDF text fixture generation may not yield text extractable by `pypdf`; verify early with `parse_document`.
- Browser integration tests are opt-in and slower; keep assertions focused.
- DOCX source rewriting means UI row source is `.md`, not `.docx`; test both converted source and original provenance via public library record data.

## Rollback

- If the browser test exposes a real product defect, keep the failing behavior captured in the task and make the smallest UI/API/parser fix needed.
- If the generated PDF fixture is unreliable, remove it from the combined browser test and rely on existing PDF/OCR focused tests while documenting the gap.
