# Phase 1: Chunk Lineage IR

## Goal

Add the first production-grade lineage layer to existing chunks without implementing a full `DocumentElement` / `DocumentAsset` system yet.

Phase 0 removed parser overfitting by introducing PDF parser profiles. Phase 1 should make every retrievable chunk traceable enough for future evidence building, admin inspection, feedback, and `/retrieve` context-pack work.

## Background / Known Context

- Current graph nodes are built from `Chunk` objects and expose `node_id`, `anchor_key`, text, header, path, source file, and metadata.
- `node_id` is graph-local and rebuild-local; it must not become a durable external reference.
- Existing `chunk_identity.json` provides rebuild reuse keys, but those keys are not a full API-facing lineage contract.
- Manual metadata already mirrors `manual_id` into generic document fields such as `doc_id`, `domain`, `doc_type`, and `attributes`.
- Phase 1 must not introduce full durable `DocumentElement` / `DocumentAsset` storage.

## Requirements

- Add stable lineage metadata to chunks/graph nodes:
  - `doc_id`
  - `chunk_id`
  - `element_ids`
  - `page_start`
  - `page_end`
  - `section_path`
  - `asset_refs`
  - `parser_profile`
  - `parser_version`
- For Markdown/TXT chunks, generate synthetic `element_ids` deterministically from document identity, section path, and chunk position/content.
- For PDF chunks, preserve current page metadata and add the same lineage fields.
- Keep existing `/search` response shape backward-compatible; new lineage fields should appear inside metadata or additive fields only.
- Keep `chunk_identity.json` compatible while making its relationship to `chunk_id` explicit.
- Qdrant payloads should carry the lineage fields needed for future filtering/debug where existing Qdrant sync already mirrors node metadata.
- Do not implement `/retrieve`, evidence builder, assets, visual evidence, OCR, or full index strategy in this task.

## Acceptance Criteria

- [ ] Existing parser/storage/search behavior remains backward-compatible.
- [ ] New chunks include `doc_id`, `chunk_id`, `element_ids`, `section_path`, `asset_refs`, `parser_profile`, and `parser_version`.
- [ ] PDF chunks still include accurate `page_start`, `page_end`, `pdf_header_source`, and `pdf_parser_profile`.
- [ ] `chunk_id` is deterministic across rebuilds when source content and parser/chunker config are unchanged.
- [ ] `chunk_id` changes when chunk text or structural identity changes.
- [ ] Incremental rebuild reuse still works and remains protected by parser signature.
- [ ] Tests cover Markdown/TXT/PDF lineage, graph node metadata, storage round-trip, and eval baseline.

## Production Readiness

- **Schema compatibility**: lineage fields are additive metadata; old clients continue to work.
- **Eval gate**: focused lineage tests, full test suite, and hashing eval CI must pass.
- **Observability/debug**: lineage coverage can be inspected through graph node metadata/debug paths without leaking raw extra text.
- **Security/permissions**: IDs must not expose unsafe filesystem paths or secrets.
- **Failure degradation**: missing optional lineage fields degrade to existing source/page metadata; invalid ID generation should fail build clearly.

## Out of Scope

- Full `DocumentElement` / `DocumentAsset` persistence.
- Asset store or asset-serving API.
- `/retrieve` Agent context API.
- Text evidence builder.
- Sentence-aware split / overlap.
- Markdown table semantic expansion.
- OCR / visual embedding.
