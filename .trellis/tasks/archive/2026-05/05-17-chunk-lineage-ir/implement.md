# Implementation Plan — Chunk Lineage IR

## Stage 1: Lineage Helpers

- [x] Add parser lineage constants/helpers in the parser layer.
- [x] Add deterministic `doc_id`, `chunk_id`, and synthetic `element_ids` derivation.
- [x] Keep IDs safe: no absolute paths or raw secrets in ID payloads.

## Stage 2: Parser Integration

- [x] Add lineage to Markdown chunks.
- [x] Add lineage to TXT chunks.
- [x] Add lineage to PDF chunks while preserving `page_start`, `page_end`, `pdf_header_source`, and `pdf_parser_profile`.
- [x] Ensure `_post_process` recomputes or preserves distinct lineage after splits/merges.

## Stage 3: Graph / Storage Integration

- [x] Ensure graph nodes carry lineage metadata.
- [x] Ensure storage round-trip preserves lineage metadata.
- [x] Ensure Qdrant payload metadata path remains additive.
- [x] Keep `chunk_identity.json` behavior compatible.

## Stage 4: Tests

- [x] Parser tests for Markdown/TXT lineage.
- [x] Parser tests for PDF lineage.
- [x] Determinism test for same source/content/config.
- [x] Change test proving chunk id changes when text changes.
- [x] Storage/graph test for lineage fields.
- [x] Incremental rebuild regression.

## Validation

```bash
.venv/bin/python -m pytest tests/unit/test_parser.py tests/unit/test_storage_state.py tests/unit/test_manual_library.py::test_incremental_rebuild_reuses_unchanged_dirty_manual_chunk -q
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/run_eval_ci.py
```

Validation completed:

- `.venv/bin/python -m pytest tests/unit/test_parser.py tests/unit/test_storage_state.py tests/unit/test_manual_library.py -q`
- `.venv/bin/python -m pytest tests/ -q`
- `.venv/bin/python scripts/run_eval_ci.py`

## Review Gates

- **Gate A**: `node_id` remains internal and rebuild-local.
- **Gate B**: `chunk_id` is deterministic for stable chunks.
- **Gate C**: Lineage fields are additive and backward-compatible.
- **Gate D**: No `/retrieve`, evidence builder, asset store, OCR, or full Document IR is introduced.
