# Implementation Plan — Production Chunker

## Direction Gate 0: Before Implementation

- [x] Confirm this task only changes chunking/parsing behavior and additive metadata.
- [x] Confirm no `/retrieve`, evidence builder, asset store, OCR, visual embedding, or full Document IR is introduced.
- [x] Confirm chunking rules are profile-neutral and do not hard-code appliance/product-manual vocabulary.
- [x] Record baseline parser/eval behavior before changing chunker logic.

Gate 0 notes:

- Scope remains limited to parser/chunker/config/signature/tests.
- Baseline before chunker changes: focused parser/config/storage/incremental tests passed (`51 passed`); eval CI passed all 8 suites with hashing baseline.

## Stage 1: Config and Signature

- [x] Add parser config for overlap if needed.
- [x] Include new chunker config in `chunk_identity.py::parser_signature`.
- [x] Add config validation tests for defaults and invalid values.

## Stage 2: Sentence-Aware Split

- [x] Replace last-resort hard split with paragraph/sentence-aware split.
- [x] Keep hard split only as final fallback.
- [x] Add tests for English and CJK sentence boundaries.
- [x] Add tests for pathological long text with no punctuation.

## Stage 3: Overlap

- [x] Apply bounded deterministic overlap to split siblings.
- [x] Ensure overlap does not merge unrelated headings/sections.
- [x] Ensure split chunks get distinct lineage `chunk_id`s.
- [x] Add tests for overlap content and ID uniqueness.

## Stage 4: Table-Aware Handling

- [x] Detect simple Markdown pipe tables.
- [x] Preserve small tables intact when under `max_chars`.
- [x] Split large tables on row boundaries.
- [x] Repeat table header when splitting large tables if useful.
- [x] Add additive metadata for table chunks only if it remains stable and safe.

## Direction Gate 1: After Core Chunker Changes

- [x] Inspect representative Markdown/TXT/PDF/table outputs.
- [x] Confirm no domain-specific vocabulary was introduced.
- [x] Confirm product-manual fixtures still produce sensible chunks.
- [x] Confirm lineage metadata remains present after chunking.

Gate 1 notes:

- Inspected Markdown, TXT, generic PDF, and Markdown table samples.
- Table chunks avoid overlap pollution and split on row boundaries with repeated headers.
- PDF chunks still carry page metadata and `pdf:generic` lineage profile.
- No appliance/product-manual terms were added to chunking rules.

## Stage 5: Integration Tests

- [x] Parser tests for Markdown/TXT/PDF chunking.
- [x] Storage/graph lineage round-trip remains green.
- [x] Incremental rebuild parser signature regression.
- [x] Qdrant payload behavior remains additive.

## Direction Gate 2: Before Commit

- [x] Run focused tests.
- [x] Run full tests.
- [x] Run eval CI.
- [x] Record chunk-count/eval trade-offs if any.

Gate 2 notes:

- Focused tests passed (`58 passed`) after chunker changes.
- Full test suite passed (`495 passed, 2 skipped`).
- Eval CI passed all 8 hashing baseline suites with the same reported metrics as Gate 0.
- Trade-off: table chunks may slightly exceed `max_chars` when necessary to preserve an individual table row with its header; this is intentional to avoid breaking table semantics.

## Validation

```bash
.venv/bin/python -m pytest tests/unit/test_parser.py tests/unit/test_config.py tests/unit/test_storage_state.py tests/unit/test_manual_library.py::test_incremental_rebuild_reuses_unchanged_dirty_manual_chunk -q
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/run_eval_ci.py
```

Validation completed:

- `.venv/bin/python -m pytest tests/unit/test_parser.py tests/unit/test_config_env.py tests/unit/test_storage_state.py tests/unit/test_manual_library.py::test_incremental_rebuild_reuses_unchanged_dirty_manual_chunk tests/unit/test_manual_library.py::test_incremental_rebuild_falls_back_when_overlap_config_changes -q`
- `.venv/bin/python -m pytest tests/ -q`
- `.venv/bin/python scripts/run_eval_ci.py`

## Review Gates

- **Gate A**: `node_id` remains internal; `chunk_id` remains lineage identity.
- **Gate B**: chunker behavior is profile-neutral and not appliance-specific.
- **Gate C**: parser/chunker config changes protect incremental rebuild identity.
- **Gate D**: table handling improves retrieval readiness without implementing Phase 2.5 indexes.
- **Gate E**: `/search` remains backward-compatible.
