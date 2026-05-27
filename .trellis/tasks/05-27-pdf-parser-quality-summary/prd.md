# PDF parser quality summary

## Goal

Expose bounded, user-understandable PDF parsing quality signals after managed-library rebuilds so operators can tell whether a real PDF was indexed cleanly, had missing-text pages, or needs OCR follow-up.

## User Value

Real text-based PDFs already index successfully, but parser warnings such as rotated text are currently visible mainly as raw logs. Users and operators need a concise quality summary in the browser workflow before they can trust answers or decide to enable OCR / replace a scanned document.

## Confirmed Facts

- PDF parsing lives in `src/tagmemorag/parser.py`; `_parse_pdf()` extracts per-page text and already invokes OCR only for pages with no usable native text.
- OCR has a default-off foundation and returns `OCRSummary`, which is already merged into `GraphState.meta["ocr"]`.
- Manual Library diagnostics already returns `last_rebuild` metadata and the admin page renders diagnostics cards.
- Real PDF testing documented repeated `Rotated text discovered. Output will be incomplete.` warnings and recommended bounded operator-facing parser warning summarization.

## Requirements

- Collect PDF quality summary during build without changing chunk text, ranking, or parser suffix support.
- Include bounded counts:
  - document count;
  - total pages;
  - pages with native extractable text;
  - pages with no usable native text;
  - pages that produced OCR text;
  - bounded parser warning counts.
- Capture common parser extraction warnings such as rotated text without surfacing raw document text.
- Store the summary in build metadata so diagnostics can return it after rebuild.
- Surface the summary through Manual Library diagnostics and the admin diagnostics cards.
- Preserve existing `.md`, `.txt`, `.pdf`, `.docx` intake behavior and OCR behavior.
- Add focused parser/build/API/static UI tests.

## Acceptance Criteria

- [ ] PDF build metadata includes `meta["pdf_quality"]` when PDFs are parsed.
- [ ] Empty-text PDF pages increment missing-text counts even when OCR is disabled.
- [ ] OCR-created PDF pages increment OCR-created counts when OCR is enabled.
- [ ] Rotated-text or equivalent parser extraction warnings are captured as bounded warning keys/counts.
- [ ] `GET /manual-library/diagnostics` returns the latest PDF quality summary.
- [ ] Manual Library diagnostics UI displays a PDF quality card and recommendation when missing-text pages or parser warnings exist.
- [ ] Existing retrieval/indexing behavior is unchanged.
- [ ] Focused tests and `git diff --check` pass.

## Out Of Scope

- Adding a production OCR engine such as PaddleOCR/Tesseract.
- Reprocessing existing built artifacts without a rebuild.
- Per-page detailed UI drill-down.
- Persisting raw parser warning text or raw document snippets.
- Native `.doc` support.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
