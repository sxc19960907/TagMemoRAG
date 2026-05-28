# Browser Multiformat Document Intake Design

## Boundary

This task verifies and hardens the browser-first managed manual intake path. It does not change the core parser architecture unless testing exposes a user-facing defect.

In scope:

- Manual Library upload dialog and public `/manuals` upload endpoint.
- Managed library rebuild and diagnostics endpoints.
- QA page answer flow after rebuild.
- Default browser-supported formats: Markdown, TXT, text PDF, DOCX, plus the existing opt-in scanned PDF OCR browser smoke.

Out of scope:

- HTML in the default native parser path. HTML requires `parser.provider=langchain` and should remain a separate provider-specific slice.
- Binary legacy `.doc` support.
- Adding new production parser dependencies.

## Current Contracts

- `supported_document_suffixes(ParserConfig(provider="native"))` returns `.md`, `.txt`, `.pdf`.
- Manual Library accepts `.docx` by rewriting metadata to a `.md` source and converting OpenXML paragraph text to Markdown before indexing.
- The original DOCX source is retained in metadata as `source_format=docx` and `remote_id=<original .docx path>`.
- Text PDF extraction uses `pypdf`; scanned PDF requires OCR enabled by config and system commands.
- Diagnostics expose PDF quality and OCR status as summarized metadata.

## Test Data Strategy

- Generate TXT and DOCX fixtures inside the test with standard library file/zip helpers.
- Generate a small text-based PDF with `pypdf.PdfWriter` and page annotations/text metadata only if it produces searchable text; otherwise use a deterministic minimal fixture already supported by the parser tests. No new dependencies.
- Reuse the existing scanned PDF OCR smoke for image-only PDF behavior instead of merging it into a larger slower test.

## Browser Flow

Add a focused opt-in browser integration test to `tests/integration/test_browser_admin_ui.py`:

1. Start the app with hashing embeddings and noop answer generation.
2. Open Manual Library for `default`.
3. Upload TXT, text PDF, and DOCX through the upload dialog with `trigger_rebuild` checked.
4. Wait after each upload/rebuild until the target manual row is searchable and has chunks.
5. Inspect library state/diagnostics through public endpoints from the browser page.
6. Ask QA questions that should cite each uploaded format.

The existing scanned PDF OCR browser smoke remains the acceptance proof for scanned image PDFs with OCR enabled.

## Compatibility

- OCR remains default-off in ordinary config.
- The new test stays behind `TAGMEMORAG_RUN_BROWSER_UI=1`, consistent with existing browser integration tests.
- If text PDF fixture generation cannot produce extractable text with existing dependencies, switch to a narrower assertion that validates upload/rebuild diagnostics for PDF while keeping QA proof for TXT/DOCX and scanned OCR proof in the existing test.

## Safety

- Do not log or expose full extracted document text in diagnostics.
- Rebuild failures must preserve the previous graph; tests should use fresh temp KBs to avoid damaging local data.
- Keep generated samples in pytest temp dirs or existing `.tmp/ocr-samples`; do not commit large binaries.
