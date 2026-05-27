# PDF Parser Quality Summary Design

## Boundary

Keep PDF quality as parser/build diagnostics, not retrieval behavior. The parser records safe counts while producing the same chunks as today; `build_kb()` merges summaries into `GraphState.meta`; Manual Library diagnostics exposes the latest meta summary.

## Data Contract

Add a small dataclass in `parser.py` or a helper module:

- `PDFQualitySummary.documents`
- `PDFQualitySummary.pages_total`
- `PDFQualitySummary.pages_with_text`
- `PDFQualitySummary.pages_missing_text`
- `PDFQualitySummary.ocr_pages_created`
- `PDFQualitySummary.warning_counts: dict[str, int]`

Serialized as `meta["pdf_quality"]`:

```json
{
  "documents": 1,
  "pages_total": 12,
  "pages_with_text": 10,
  "pages_missing_text": 2,
  "ocr_pages_created": 1,
  "warning_counts": {"rotated_text": 3}
}
```

Only bounded keys and counts are stored. No raw PDF text, page body, full warning text, local absolute paths, or provider internals are stored.

## Data Flow

```text
build_kb
  -> parse_document_for_config
  -> parse_document_with_ocr_summary
  -> _parse_pdf
  -> ParsedDocument(chunks, ocr_summary, pdf_quality)
  -> state meta["pdf_quality"]
  -> manual_library_diagnostics.last_rebuild.pdf_quality
  -> admin diagnostics card + recommendation
```

## Warning Capture

`pypdf` may emit warnings to stderr/logging for rotated text. The MVP captures warnings produced during page text extraction with Python warning capture around `_extract_pdf_page_text(page)`. It maps known text such as `Rotated text discovered` to `rotated_text`; unknown warning strings become bounded `parser_warning` or sanitized short keys.

If a fake page/test warning is emitted, it exercises the same capture path.

## Compatibility

- `.md`, `.txt`, `.docx` materialized Markdown behavior remains unchanged.
- PDF chunks and OCR trigger policy remain unchanged.
- No new production dependency.
- Diagnostics clients that ignore unknown fields remain compatible.

## UI

Manual Library diagnostics adds a PDF Quality card:

- Normal: `N pages, M missing`
- Warning badge when `pages_missing_text > 0` or warning counts are non-empty.

Recommendations add:

- `review_pdf_quality` when warnings or missing-text pages exist.

## Rollback

Remove the summary field, diagnostics pass-through/card, recommendation, and tests. Parser chunking and indexing behavior should be unaffected.
