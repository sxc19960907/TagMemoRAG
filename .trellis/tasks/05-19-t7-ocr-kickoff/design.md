# T7 Phase 7A OCR kickoff — Design

## Scope

Add a default-off OCR text ingestion foundation for PDF pages whose native
`pypdf` extraction yields no useful text. OCR text is converted into normal
chunks and flows through the existing graph/vector/lexical/retrieve/answer
pipeline. T7 does not ship a production OCR engine.

## Module Layout

```text
src/tagmemorag/ocr/
  __init__.py
  base.py
  provider.py
```

- `base.py`: result dataclasses and `OCRProvider` protocol.
- `provider.py`: provider factory and deterministic fixture provider.
- `config.py`: `OCRConfig`.
- `parser.py`: optional OCR provider parameter for PDF parsing.
- `state.py`: passes configured OCR provider into parsing and records OCR
  summary metadata.

## Config

`Settings.ocr` defaults:

```yaml
ocr:
  enabled: false
  provider: deterministic
  version: ocr.v1
  trigger: missing_text
  strict_extraction: false
```

Provider values in T7: `deterministic`.

## OCR Provider Contract

`OCRProvider.recognize_pdf_page(context) -> OCRPageResult`

Context contains source path, source file, page number, doc id, KB name, and
source metadata. The provider returns text plus warnings. Provider errors are
caught by parser/state unless strict mode is enabled.

The deterministic provider reads optional fixture text from metadata:

```python
metadata["ocr_pages"] = {"2": "Recognized text"}
```

This lets tests exercise parser and rebuild behavior with no OCR dependency.

## Parser Data Flow

1. `_parse_pdf()` extracts native page text with `pypdf`.
2. `_pdf_lines()` cleans native text.
3. If lines are present, existing native PDF chunk behavior is preserved.
4. If lines are empty and OCR is enabled, call `OCRProvider`.
5. OCR text is cleaned with `_pdf_lines()` and chunked by `_pdf_page_chunks()`.
6. OCR chunks carry:
   - `ocr_provider`
   - `ocr_version`
   - `ocr_trigger`
   - `ocr_source="pdf_missing_text"`
   - `pdf_header_source` like native chunks
   - `parser_profile="pdf_ocr:<pdf_profile>"`
7. OCR summary counts attempted/created/skipped/failed and safe failure reasons.

## Rebuild Integration

`build_kb()` creates the OCR provider from settings and passes it to
`parse_document()`. It aggregates parser OCR summaries into `state.meta["ocr"]`.

When OCR is disabled, no provider is created and existing parsing behavior stays
unchanged.

## Assets

T7 does not create page snapshot duplicates. OCR chunks keep page metadata and
can later be related to page snapshots by source file/doc id/page number. The
existing `ocr_layer` asset type remains reserved for a future richer provider.

## Error Handling

Provider failures:

- default: skip OCR text for that page, increment failure summary, and continue.
- strict mode: raise a structured service error and fail rebuild.

Summaries store only provider names, counts, and bounded failure reasons; raw
OCR text is never logged or stored in metadata summaries.

## Tests

- Config defaults and YAML override.
- OCR provider deterministic text lookup.
- Parser disabled behavior unchanged.
- Empty PDF page becomes OCR chunk when enabled.
- Native text page does not call OCR.
- Provider failure degrades and records summary.
- `build_kb()` can retrieve OCR-only text.
- Existing parser/API/answer tests remain green.
