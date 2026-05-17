# Technical Design — Product manual PDF structure and retrieval quality

> Parent document: [prd.md](./prd.md)

## 1. Design Intent

This task should improve product-manual PDF retrieval by improving input structure. The current wave/search pipeline works best on structured Markdown-like chunks; product-manual PDFs need to be converted into similarly meaningful chunks.

The target is a pragmatic parser upgrade:

```text
PDF page text -> layout/line extraction -> section-like blocks -> Chunk(metadata includes page range)
```

Do not turn this task into a general document-understanding platform.

## 2. Current Flow

```text
parse_document()
  if .pdf:
    PdfReader.pages
    page.extract_text()
    Chunk(header="Page N", path=("Page N",), text=whole_page)
  _post_process(max_chars/min_chars)
```

Problems:

- page chunks mix unrelated topics
- `path` has no semantic hierarchy
- chunk start positions are synthetic line numbers
- eval can only weakly route by source/category

## 3. Proposed Flow

```text
parse_document(.pdf)
  -> extract per-page text in layout-friendly mode
  -> normalize lines
  -> detect candidate section headings
  -> group following lines into blocks
  -> create Chunk(
       header=detected heading or Page N,
       path=(manual section heading,) or (Page N,),
       metadata={..., page_start, page_end, pdf_header_source}
     )
  -> _post_process()
```

## 4. Parser Contracts

### 4.1 PDF chunk metadata

Every PDF chunk should include:

```python
{
    "page_start": 12,
    "page_end": 12,
    "pdf_header_source": "detected" | "page_fallback",
}
```

If a chunk spans multiple pages, page_start/page_end should represent the inclusive range.

### 4.2 Header/path behavior

- Detected section: `header=<section title>`, `path=(<section title>,)`.
- Page fallback: `header="Page N"`, `path=("Page N",)`.
- If a detected section is split by `_post_process`, split parts keep the section header and page metadata.

### 4.3 Backward compatibility

- Markdown/TXT behavior must remain unchanged.
- Existing manual metadata and generic document metadata must be preserved.
- Saved graph/result shapes can add metadata but should not remove existing fields.

## 5. Heading Detection Heuristics

MVP deterministic rules:

- Normalize whitespace and remove empty lines.
- Candidate heading if line is short enough and one of:
  - starts with numbered heading pattern (`1`, `1.2`, `3.4.5`, with punctuation)
  - matches common product-manual section keywords in English/Chinese
  - title-like / uppercase line with few punctuation marks
- Reject likely non-headings:
  - very long lines
  - lines ending with sentence punctuation after many words
  - isolated page numbers
  - obvious table-of-contents dotted leader lines

The parser should be conservative. False negatives fall back to page chunks; false positives can harm retrieval by fragmenting procedures.

## 6. Chunking Strategy

- Build blocks from heading to next heading on the same page.
- If a page has no detected heading, keep page fallback chunk.
- If text before the first heading is meaningful, attach it to page fallback or the first heading depending on length.
- Run existing `_post_process` to enforce `max_chars`/`min_chars`.

Follow-up if MVP is weak:

- Use visitor font information from `pypdf` for stronger heading confidence.
- Consider optional `pymupdf` or `pdfplumber`.
- Consider generated Markdown sidecars for stable human-auditable parse output.

## 7. Eval Plan

### 7.1 Strict realmanuals cases

Update `tests/fixtures/eval/realmanuals.jsonl` by replacing placeholder relevant entries for at least 8 cases.

Stable matching should prefer:

- `source_file`
- `text_contains`
- `metadata` fields such as product category/model
- page metadata if added to eval matching/reporting path

### 7.2 Diagnostic report

Add or extend a script to report:

- chunk count by manual
- detected vs fallback PDF chunks
- sample headers
- category routing metrics
- strict eval metrics for labeled cases

## 8. Risks

- `pypdf` text extraction may not preserve enough visual structure for reliable headings.
- Product manuals have tables/procedure layouts that line heuristics can misread.
- Real PDFs are not committed in all environments, so tests must use fake PDF reader/unit fixtures for deterministic CI.
- If parser metadata changes chunk identity too much, incremental rebuild/Qdrant reuse behavior needs regression coverage.

## 9. Rollback

- Config rollback is not planned for parser behavior initially; code rollback can restore page-level `_parse_pdf`.
- Keep page fallback path so parser failure does not block indexing text-based PDFs.
- Strict realmanuals gating should remain opt-in until parser quality is proven.
