# Phase 2.5: Indexing Strategy and Index Schema

## Goal

Define the indexing model that connects Phase 1 lineage and Phase 2 production chunking to future Phase 3 `/retrieve`, text evidence, and Agent context packs.

This is primarily a design/contract task. It should make explicit which objects enter which indexes, how IDs map across graph/vector/Qdrant/debug/evidence layers, how hybrid scores are combined, and how incremental rebuilds reuse or refresh each index. It should not implement `/retrieve`, evidence building, parent chunks, asset storage, OCR, visual embeddings, or learned fusion.

## Background / Known Context

- Phase 1 added stable chunk lineage metadata, including `doc_id`, `chunk_id`, synthetic `element_ids`, `section_path`, `asset_refs`, `parser_profile`, and `parser_version`.
- Phase 2 added sentence-aware splitting, configurable overlap, table-aware chunk splitting, and additive metadata such as `chunk_kind` / `split_reason`.
- Current graph nodes are still existing `Chunk` objects; `node_id` remains rebuild-local.
- Current Qdrant point ids still use numeric `node_id`; Qdrant payloads include safe fields such as `kb_name`, `node_id`, `build_id`, `chunk_identity_key`, `doc_id`, `chunk_id`, `manual_id`, `source_file`, and `text_hash`.
- Current search is still `/search` over vector/lexical/metadata/graph WAVE paths.
- Future Phase 3 needs stable evidence/context contracts, so indexes must have a clear shape before `/retrieve` is implemented.

## Requirements

- Produce an ID full-map covering:
  - `doc_id`
  - `chunk_id`
  - synthetic `element_ids`
  - future `parent_chunk_id`
  - future `asset_id`
  - `chunk_identity.json` identity key
  - graph `node_id`
  - Qdrant point id
  - request-scoped `citation_id` and `context_item_id`
- Define index participation for current and future object types:
  - child text chunks
  - parent/context chunks
  - table chunks
  - table rows
  - asset-derived text
  - OCR text
  - image captions
  - visual embeddings
- Define Qdrant payload schema direction for current Phase 2 fields and future Phase 3/4 fields.
- Define graph topology strategy:
  - current graph nodes remain child/retrieval chunks;
  - parent chunks should be context expansion unless eval proves otherwise;
  - table chunks remain normal chunks for now, with future table-row indexing decision deferred.
- Define conservative hybrid fusion strategy:
  - current pipeline ranking remains default;
  - any new score components must be explainable;
  - learned/complex fusion is deferred until labeled eval/feedback data exists.
- Define eval gates for indexing changes:
  - retrieval hit rate;
  - citation correctness readiness;
  - table retrieval correctness;
  - metadata narrowing correctness;
  - latency and debug explainability.
- Define incremental rebuild reuse rules for each index under:
  - unchanged source;
  - metadata-only update;
  - parser profile change;
  - chunker config/version change;
  - table handling change;
  - future asset/OCR regeneration.
- Keep Phase 2.5 as a contract task unless a tiny code/doc addition is required to preserve the roadmap.

## Production Readiness

- **Schema compatibility**: index schema changes must be versioned and additive where possible; current graph/Qdrant artifacts remain load-compatible.
- **Eval gate**: future indexing changes must compare against stored baselines and document intentional trade-offs before becoming default.
- **Observability/debug**: retrieval debug should expose index participation and score components without leaking raw query tokens, snippets, vectors, or unsafe path lists.
- **Security/permissions**: Qdrant payloads and debug artifacts must store only safe IDs/metadata; asset access must later be authorized against KB/document permission context.
- **Failure degradation**: if one index is missing or stale, retrieval should fall back to the safest available path rather than returning corrupt mixed results.

## Acceptance Criteria

- [ ] `design.md` contains a clear ID full-map with stable vs rebuild-local vs request-scoped IDs.
- [ ] `design.md` defines which current and future objects enter vector, lexical, metadata/facet, graph, asset-text, OCR, and visual indexes.
- [ ] `design.md` defines the conservative default hybrid fusion approach and a future fusion exploration plan.
- [ ] `design.md` defines Qdrant payload schema direction and point-id migration stance.
- [ ] `design.md` defines incremental rebuild reuse/refresh rules by index and change type.
- [ ] `design.md` defines debug/observability fields needed for Phase 3 without leaking raw sensitive data.
- [ ] `implement.md` breaks future implementation into small PR-sized follow-up tasks.
- [ ] Direction check confirms this task prepares Phase 3 and does not implement Phase 3 prematurely.

## Out of Scope

- Implementing `/retrieve`, evidence builder, citations, or context packs.
- Changing graph node ids or Qdrant point ids in this task.
- Implementing parent chunks, asset store, OCR, visual embeddings, or image vector indexes.
- Implementing learned fusion or a new reranker.
- Replacing current `/search` ranking behavior.
