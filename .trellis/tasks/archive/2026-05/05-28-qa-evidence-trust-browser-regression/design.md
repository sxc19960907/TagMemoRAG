# QA Evidence Trust and Browser Regression Design

## Boundary

This task spans the retrieve/QA payload, QA page rendering, and browser tests. It does not introduce new retrieval algorithms, new model providers, or new document parsers.

## Data Flow

1. Retrieval builds `evidence[]` from `Result` objects.
2. Evidence is returned through `/retrieve` and, when `include_retrieve=true`, `/qa/answer`.
3. QA page renders `answer.citations` as clickable chips and `retrieve.evidence` as source cards.
4. Browser tests exercise the page as a user would.

## Additive Evidence Contract

Extend each evidence item with a safe `provenance` object:

```json
{
  "source_format": "docx|pdf|txt|md|",
  "source_file": "stored/indexed/source.md",
  "original_source_file": "uploaded/original.docx",
  "display_source": "uploaded/original.docx",
  "page_range": [1, 2],
  "parser_profile": "pdf_ocr:product_manual",
  "ocr": true
}
```

Rules:

- `source_file` remains the indexed/stored source for compatibility.
- `original_source_file` is populated only from safe metadata such as `remote_id`.
- `display_source` prefers original source when it differs from indexed source; otherwise it uses `source_file`.
- `ocr` is true only for OCR-derived chunks.
- Do not include local absolute paths, blob keys, checksums, vectors, raw OCR text, or raw diagnostics.

## UI Rendering

QA Sources cards should show:

- Citation id and readable strength label.
- Display source, plus converted/indexed source note when different.
- Page or page range when present.
- OCR marker when provenance says the evidence is OCR-derived.
- Section path and cited passage summary/expand behavior as today.

The design stays compact because this is an operational QA tool, not a marketing page.

## Browser Regression

Add a focused user-flow regression over existing public/browser routes:

- Upload a DOCX from the QA page or Manual Library.
- Ask a question that produces citations.
- Assert citation chips, source cards, provenance labels, source expansion, citation focus, feedback review link, history restore, language switch, and mobile layout.
- Reuse existing helpers where possible.

The existing scanned-PDF OCR and multiformat browser tests remain the format-specific smoke coverage.

## Compatibility

- All backend fields are additive.
- Existing clients reading only `source_file`, `section_path`, `text`, and `citation_id` keep working.
- Stored session history sanitization must keep enough provenance for restored answers while still bounding payload size.
