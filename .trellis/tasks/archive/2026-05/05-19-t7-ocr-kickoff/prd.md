# T7 Phase 7A OCR kickoff

## Goal

Ship the Phase 7A OCR foundation: scanned or image-only PDF pages can produce
retrievable text that flows through the existing parser, chunker, graph, vector,
lexical, `/retrieve`, and `/answer` paths. OCR is a text-ingestion enhancement,
not a parallel visual retrieval path.

## User Value

Product manuals often contain scanned pages, screenshots, tables, labels, or
low-quality embedded text. Today those pages can become invisible to search when
`pypdf` extracts no useful text. T7 should recover useful text for those pages
while keeping rebuild behavior deterministic and deployable without mandatory
heavy OCR dependencies.

## Confirmed Facts

- `parse_document()` already supports `.pdf` through `pypdf` layout extraction.
- PDF chunks already carry `page_start`, `page_end`, `pdf_header_source`,
  `pdf_parser_profile`, `parser_profile`, `parser_version`, `chunk_id`, and
  `asset_refs`.
- The asset model already reserves `DocumentAsset.type="ocr_layer"` and an
  `ocr_text` field.
- PDF page snapshots already exist behind `assets.enabled` and
  `assets.pdf_page_snapshots_enabled`; they are stored as `page_snapshot`
  `DocumentAsset`s.
- `build_kb()` currently parses document text before asset extraction.
- Generation trigger comparison currently includes parser/chunker/index/model
  versions, but no OCR-specific version field.
- T8 visual retrieval depends on OCR, but OCR itself should feed the existing
  text retrieval path first.

## Requirements

- OCR is disabled by default.
- Add a vendor-neutral OCR provider boundary so the rebuild path is not coupled
  to one OCR engine.
- Ship a deterministic local test provider; do not require network or native OCR
  binaries for default tests.
- MVP triggering policy: run OCR only for PDF pages where `pypdf` yields no
  useful text.
- OCR output re-enters the existing chunker as text chunks, with page metadata
  and OCR-specific lineage.
- OCR-derived chunks must be distinguishable from native PDF text chunks.
- OCR failures must degrade safely: failed OCR pages do not fail rebuild unless
  strict mode is enabled.
- If page snapshots are enabled, OCR should reuse or relate to page-level asset
  identity instead of creating an incompatible duplicate page concept.
- Expose rebuild metadata that lets operators see OCR attempted/created/skipped
  and failure reasons without logging raw OCR text.
- Preserve existing `/search`, `/retrieve`, `/answer`, and asset behavior when
  OCR is disabled.

## Decisions

### D1 MVP trigger: missing-text PDF pages only

Run OCR only when the PDF page has no useful text after current `pypdf`
extraction and line cleanup.

Reasoning: this keeps rebuild cost low, avoids duplicate native/OCR content, and
targets the clearest user-visible gap: scanned pages that currently vanish.

### D2 Provider posture: boundary first, deterministic provider now

T7 defines an `OCRProvider` protocol and ships a deterministic local provider
for tests. Real OCR engines or API providers are follow-up implementations.

Reasoning: backend selection has many deployment trade-offs. The first task
should stabilize contracts and indexing behavior without hard-coding a heavy
dependency.

### D3 Layout stance: page-block text MVP

The MVP treats OCR result text as page-level blocks, preserving page number and
line order. Layout-aware tables/regions are deferred.

Reasoning: page-block OCR is enough to recover answerable text from scanned
manual pages and fits the existing chunker. Table structure and bounding boxes
can later add richer chunks/assets without changing the MVP contract.

### D4 Lineage: separate OCR version

OCR output gets its own `ocr_version`/`ocr_provider` lineage fields instead of
being hidden inside `parser_version`.

Reasoning: OCR changes can alter generated chunks and embeddings independently
from parser changes, so rebuild triggers and debugging should expose that axis.

### D5 Page snapshot relation: reuse page identity by page number/source

For MVP, OCR chunks reference page metadata and can attach matching page snapshot
asset ids when snapshots are enabled. They do not create a second page snapshot.
An `ocr_layer` asset may record OCR text/metadata later, but raw OCR text should
not be required in asset manifests for retrieval to work.

Reasoning: page snapshots already exist as visual evidence assets. Duplicating
page images would waste storage and confuse citation/asset references.

### D6 Provider scope: deterministic provider only in T7

T7 ships only the protocol plus deterministic provider used by tests and local
fixtures. Production OCR providers are follow-up tasks.

Reasoning: the important first contract is how OCR text enters parser/chunker,
lineage, rebuild metadata, and retrieval. A production backend choice adds
dependency, deployment, latency, and accuracy trade-offs that should not blur the
foundation task.

## Out Of Scope

- Choosing or integrating a production OCR engine/API.
- OCR for non-PDF image files.
- Layout-aware table reconstruction, region crops, or bounding-box-level chunks.
- Visual embeddings or visual reranking; that is T8.
- Background OCR workers or asynchronous rebuild queues.
- LLM-based OCR correction.

## Acceptance Criteria

- [x] `Settings.ocr` exists and defaults to disabled.
- [x] A provider protocol and deterministic test provider exist.
- [x] PDF pages with native extracted text keep existing behavior when OCR is
      disabled or when OCR trigger says no OCR is needed.
- [x] PDF pages with no native text can produce OCR chunks when OCR is enabled.
- [x] OCR chunks carry page metadata plus `ocr_provider`, `ocr_version`, and a
      parser/chunk lineage that makes them distinguishable from native PDF
      chunks.
- [x] OCR failures are recorded in safe low-cardinality rebuild metadata and do
      not expose raw OCR text.
- [x] Existing parser, storage, API, retrieve, and answer tests remain green.
- [x] Focused OCR tests cover disabled, missing-text trigger, native-text skip,
      provider failure, and rebuild integration.

## Eval Slice

- Synthetic PDF fixture with one native-text page and one scanned/empty page.
- Retrieval query that is answerable only from OCR text.
- Regression query that is answerable from native PDF text and should not gain
  duplicate OCR chunks.
- Existing `/retrieve` and `/answer` API regression tests.

## Open Questions

- None blocking implementation.
