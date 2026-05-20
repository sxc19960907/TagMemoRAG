# Implementation Plan — Phase 0 Only

> Parent docs: [prd.md](./prd.md) · [design.md](./design.md)

## Decision

The architecture roadmap is intentionally larger than the first implementation. The first PR must deliver only Phase 0: stop parser/chunker overfitting and make the current PDF heading heuristics profile-driven.

Do not implement `DocumentElement`, `DocumentAsset`, `/retrieve`, OCR, page snapshots, or multimodal retrieval in this PR.

Every phase in the mainline roadmap must include production readiness work for schema compatibility, eval gates, observability/debug, security/permissions, and failure degradation.

## Phase 0 Goal

Turn the current hard-coded product-manual PDF heading vocabulary into an explicit, configurable parser profile while preserving current product-manual behavior and proving non-appliance documents are not forced through appliance-specific assumptions.

## Work Items

### 1. Parser Profile Contract

- [x] Add a small parser profile/config contract for PDF heading hints.
- [x] Define the default profile behavior.
- [x] Define a `product_manual` profile containing the current product-manual keyword hints.
- [x] Keep generic heading detection based on structure/patterns, not domain vocabulary.

### 2. Config Wiring

- [x] Add parser config keys for selecting profile and/or heading hint list.
- [x] Keep backward-compatible defaults for existing product-manual builds.
- [x] Avoid broad API changes.

### 3. Parser Refactor

- [x] Remove domain keyword dependency from core `_is_pdf_heading` logic.
- [x] Pass profile hints into PDF parsing helpers.
- [x] Keep page fallback behavior unchanged.
- [x] Keep page metadata (`page_start`, `page_end`, `pdf_header_source`) unchanged.

### 4. Tests

- [x] Add test that product-manual profile preserves current product-manual heading behavior.
- [x] Add test that generic/non-appliance headings work without product-manual keywords.
- [x] Add test that appliance keyword absence does not force a document into page-only fallback when structural headings are present.
- [x] Keep existing parser/storage/eval tests green.

### 5. Docs

- [x] Update README/product manual docs to describe parser profiles as a temporary Phase 0 boundary.
- [x] Mark Phase 1 (Chunk Lineage IR) as the next architecture task, not part of this PR.

### 6. Phase 0 Production Readiness

- [x] Schema compatibility: parser config defaults remain backward-compatible.
- [x] Eval gate: product-manual behavior and generic/non-appliance behavior both pass focused tests.
- [x] Observability/debug: expose or record selected parser profile in a low-cardinality way where parser diagnostics exist.
- [x] Security/permissions: do not expose raw filesystem paths, unsafe profile names, or user-provided config values in public debug responses.
- [x] Failure degradation: explicitly configured unknown profiles fail fast with a clear config error; missing profile uses the backward-compatible default; empty hints use generic structural detection.

## Validation

```bash
.venv/bin/python -m pytest tests/unit/test_parser.py tests/unit/test_storage_state.py::test_build_kb_includes_pdf_documents -q
.venv/bin/python -m pytest tests/unit/test_metadata_narrowing.py tests/unit/test_eval_runner.py -q
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/run_eval_ci.py
```

## Review Gates

- **Gate A**: No hard-coded appliance vocabulary remains in core parser control flow.
- **Gate B**: Product-manual PDF behavior remains compatible.
- **Gate C**: Generic PDF-like content can produce section chunks through structural cues.
- **Gate D**: No Phase 1+ abstractions are partially introduced.
- **Gate E**: Phase 0 production readiness checklist is satisfied.

## Deferred Work

- `DocumentElement` / `DocumentAsset` contracts.
- Chunk Lineage IR (`doc_id`, `element_ids`, `page_start`, `page_end`, `section_path`, `asset_refs`, `parser_profile`, `parser_version`).
- Asset store and asset-serving API.
- `/retrieve` Agent context API.
- Text-only evidence builder.
- Sentence-aware split + overlap.
- Markdown table semantic expansion.
- OCR and visual embedding.
- DOCX/HTML/spreadsheet connectors.
