# M5 Manual Metadata and Tag-Aware Retrieval

## Goal

Turn product manuals into managed, metadata-rich knowledge assets instead of anonymous files. M5 adds a manual library contract, product/category/model/language/version/tags metadata, and tag-aware retrieval so future platform uploads can route, filter, and boost search using product context before or during semantic retrieval.

## Background / Known Context

- M0-M4 have delivered WAVE-RAG retrieval, API/CLI, multi-KB, API keys, cache, eval, Prometheus metrics, and OTel tracing.
- PDF ingest is being added separately: `parse_document()` can read text-based PDFs and `build_kb()` scans `.md/.txt/.pdf`.
- Product manuals now live under `product_manuals/`, with an example refrigerator manual under `product_manuals/fridge/`.
- Current `Chunk` and `Result` contracts contain `source_file`, `header`, `path`, `text`, and `anchor_key`, but no product metadata.
- Current graph nodes persist arbitrary attributes in JSON, so metadata can be added to nodes without changing the storage format shape.
- Current `/search` only selects by `kb_name`; within a KB all nodes are eligible.
- M2 already supports per-key KB allowlists. M5 should not replace KB authorization; metadata filtering is an additional retrieval control.

## Assumptions

- The first platform version can store manual metadata on disk next to source manuals; a DB-backed manual library can come later.
- Metadata cardinality is controlled: brand/category/model/language/version/tags are short strings curated at upload time.
- Tags are not secrets. They may appear in API responses, logs only in aggregate-safe forms, and eval fixtures.
- M5 targets retrieval routing/filtering and result explainability, not a full upload UI.
- OCR for scanned PDFs is out of scope; metadata can include `requires_ocr` or `text_extraction=empty` for later workflows.

## Decision Summary

### Decision: Use structured metadata plus tags

Do not rely on free-form tags alone. Store stable structured fields:

- `manual_id`
- `title`
- `brand`
- `product_category`
- `product_name`
- `product_model`
- `language`
- `version`
- `tags`

Use tags for secondary facets such as `installation`, `temperature-setting`, `troubleshooting`, `maintenance`, `fault-code`, `safety`.

### Decision: Start with file-backed manual metadata

M5 uses a local manifest/sidecar contract:

```text
product_manuals/
  fridge/
    gorenje-nrk6192.zh-CN.v1.pdf
    gorenje-nrk6192.zh-CN.v1.metadata.json
```

or a directory manifest:

```text
product_manuals/fridge/manuals.jsonl
```

MVP should support sidecar `.metadata.json` first because it travels with the source file and is easy for upload workflows to generate.

### Decision: Metadata belongs on chunks and graph nodes

When parsing/building a KB, each chunk inherits its source manual metadata. The graph node stores the same metadata so search can filter before WAVE propagation and responses can explain product provenance.

### Decision: Retrieval supports filters and simple boosts

MVP search adds optional metadata filters:

- `brand`
- `product_category`
- `product_model`
- `language`
- `manual_id`
- `tags`

Filtering is applied before vector source selection and graph propagation. Tag boost is optional and conservative: matching tags increase scores, but do not override a hard filter.

## Requirements

### 1. Manual Metadata Contract

- Define a `ManualMetadata` dataclass or Pydantic model.
- Required fields:
  - `manual_id`
  - `title`
  - `product_category`
  - `language`
  - `source_file`
- Optional fields:
  - `brand`
  - `product_name`
  - `product_model`
  - `version`
  - `tags`
  - `status`
  - `uploaded_at`
  - `checksum`
  - `notes`
- Validate safe low-cardinality values:
  - no empty `manual_id`
  - tags normalized to lower-kebab-case or documented project convention
  - duplicate `manual_id` in one build is an error

### 2. Manual Metadata Loading

- For each parsed file, load matching sidecar metadata if present.
- Sidecar naming convention:
  - `manual.pdf` -> `manual.metadata.json`
  - `manual.md` -> `manual.metadata.json`
  - `manual.txt` -> `manual.metadata.json`
- If no sidecar exists, generate minimal fallback metadata:
  - `manual_id` from source path stem or checksum
  - `title` from filename
  - `product_category` from parent directory when available
  - `language="unknown"`
  - `tags=[]`
- Metadata loading errors should produce clear `INVALID_INPUT` or build failure details, not silent partial metadata.

### 3. Chunk and Graph Metadata

- Extend `Chunk` to carry `metadata: dict[str, str | list[str] | bool | int | float]` or a typed metadata field.
- Graph nodes persist metadata fields.
- Search `Result` includes metadata needed by UI:
  - `manual_id`
  - `title`
  - `brand`
  - `product_category`
  - `product_model`
  - `language`
  - `version`
  - `tags`
- Existing response fields remain backward compatible.

### 4. Tag-Aware Search

- Extend `SearchRequest` with optional `filters`.
- Supported filters:
  - `manual_id`
  - `brand`
  - `product_category`
  - `product_model`
  - `language`
  - `tags`
- Filters use AND across fields.
- Tag list matching should be configurable or explicit:
  - MVP default: requested tags are OR within `tags`, AND with other fields.
- If filters eliminate all nodes, return an empty result set, not an error.
- Cache key must include filters and tag boost inputs.

### 5. Tag Boost / Rerank

- Add a simple deterministic boost after WAVE scores are computed:
  - exact metadata field match boost
  - tag match boost
- Keep defaults conservative and configurable.
- Do not use high-cardinality labels in metrics for tags or model names.

### 6. CLI and API UX

- CLI search supports basic filters:
  - `--brand`
  - `--category`
  - `--model`
  - `--language`
  - `--tag` repeatable
- API `/search` accepts the same filters in JSON.
- `/graph_info` or a new manual listing endpoint can expose available metadata facets if cheap.

### 7. Eval Support

- Eval expected results can match metadata fields.
- Add a small fridge eval suite using `product_manuals/fridge` metadata, but do not commit proprietary or ignored PDFs unless explicitly allowed.
- Tests use synthetic fixtures and fake/Hashing embedder, not network calls.

### 8. Documentation

- README documents:
  - product manual directory convention
  - sidecar metadata JSON example
  - search filter examples
  - how metadata improves speed and precision
- `product_manuals/README.md` includes a metadata sidecar template.

## Acceptance Criteria

- [ ] A manual sidecar metadata file is loaded during KB build and stored on graph nodes.
- [ ] Search results include manual/product metadata.
- [ ] `/search` can filter by category/model/language/tags.
- [ ] Filtered search only considers eligible nodes and returns empty results when none match.
- [ ] Query cache keys include filters so filtered and unfiltered requests cannot collide.
- [ ] Tag boost is deterministic and covered by tests.
- [ ] Existing M0-M4 tests remain green.
- [ ] README and `product_manuals/README.md` document the metadata workflow.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- Unit tests cover metadata loading, sidecar fallback, graph persistence, filter behavior, cache key behavior, and result serialization.
- API/CLI tests cover filtered search.
- Eval matching supports metadata expectations or explicitly defers it with documented rationale.
- `uv run pytest tests/ -v` passes.
- Any new conventions worth reusing are added to `.trellis/spec/backend/`.

## Out of Scope

- Browser upload UI.
- Object storage/S3.
- Database-backed manual library.
- OCR for scanned PDFs.
- LLM answer generation.
- Automatic tag generation by LLM.
- Cross-KB federated retrieval.
- Per-tag Prometheus metrics.

## Follow-Up Ideas

- Manual upload/admin API.
- Tag suggestion from filename/content.
- Product taxonomy management.
- Query classifier that routes to likely category/model before retrieval.
- Faceted search endpoint for UI filters.
- DB-backed manual registry and audit trail.
