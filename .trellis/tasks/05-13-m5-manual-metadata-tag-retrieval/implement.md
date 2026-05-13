# implement.md — M5 Manual Metadata and Tag-Aware Retrieval

## Phase A — Metadata Contract

- [x] Add `ManualMetadata` model and normalization helpers.
- [x] Add sidecar path resolver.
- [x] Add metadata loader:
  - sidecar `.metadata.json`
  - fallback metadata
  - duplicate `manual_id` detection
- [x] Add unit tests for metadata loading and validation.

Validation:

```bash
uv run pytest tests/unit/test_manual_metadata.py -v
```

## Phase B — Chunk and Graph Metadata

- [x] Extend `Chunk` with metadata while preserving existing constructor call sites.
- [x] Update parser to attach provided metadata to chunks.
- [x] Update `build_kb()` to load metadata per source file.
- [x] Update `build_graph()` to persist manual metadata on nodes.
- [x] Update `Result` and `_make_result()` to include metadata fields.
- [x] Ensure old graph JSON without metadata still loads.

Validation:

```bash
uv run pytest tests/unit/test_parser.py tests/unit/test_storage_state.py tests/unit/test_graph_wave.py -v
```

## Phase C — Search Filters

- [x] Add `SearchFilters` request model.
- [x] Extend `SearchRequest` with `filters`.
- [x] Implement node eligibility helper.
- [x] Update `wave_search()` or add wrapper to search within eligible node ids.
- [x] Ensure empty filters preserve existing ranking.
- [x] Ensure no-match filters return empty results.

Validation:

```bash
uv run pytest tests/unit/test_api.py tests/unit/test_m2_api.py -v
```

## Phase D — Tag Boost and Cache Key

- [x] Add `search.metadata_field_boost` and `search.tag_boost` config defaults.
- [x] Apply deterministic boost after WAVE scores.
- [x] Include filters and boost-relevant parameters in `_compute_cache_key()`.
- [x] Add tests for filtered/unfiltered cache separation.

Validation:

```bash
uv run pytest tests/unit/test_cache.py tests/unit/test_api.py -v
```

## Phase E — CLI and Docs

- [x] Add CLI `search` flags:
  - `--brand`
  - `--category`
  - `--model`
  - `--language`
  - repeated `--tag`
- [x] Update README with metadata sidecar example and filtered search examples.
- [x] Update `product_manuals/README.md` with sidecar template.
- [x] Add a fridge metadata example if the source PDF remains local/ignored.
- [x] Add `/manuals` endpoint exposing manual list and metadata facets for future UI filters.

Validation:

```bash
uv run pytest tests/unit/test_cli.py -v
```

## Phase F — Eval and Full Regression

- [x] Extend eval expected result matching with optional metadata fields, or document why this is deferred.
- [x] Add a tiny synthetic fixture demonstrating metadata-aware search.
- [x] Run full regression.

Validation:

```bash
uv run pytest tests/ -v
```

## Review Gates

- [x] Metadata does not introduce secrets or high-cardinality Prometheus labels.
- [x] Existing unfiltered search behavior remains compatible.
- [x] KB authorization remains based on `kb_name`; filters do not bypass M2 permissions.
- [x] Cache key includes all result-affecting inputs.
- [x] Sidecar metadata format is documented clearly enough for a future upload page to generate it.

## Follow-Up Tasks

- Upload/admin API for manual library.
- Browser UI for manual management.
- DB-backed manual registry.
- OCR pipeline for scanned PDFs.
- Query classifier for automatic product/category routing.
