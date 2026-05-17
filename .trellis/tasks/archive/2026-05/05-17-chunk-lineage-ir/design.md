# Design — Chunk Lineage IR

## Scope

Phase 1 adds lineage metadata to existing chunks while preserving the current graph/search/storage architecture.

The design deliberately keeps `Chunk` as the retrieval unit. It does not introduce durable `DocumentElement` or `DocumentAsset` tables. Synthetic ids are acceptable as long as they are deterministic and documented.

## Lineage Fields

Add these fields to chunk metadata:

- `doc_id`: stable document identity. Prefer metadata `doc_id`; fallback to `manual_id`; fallback to normalized source file.
- `chunk_id`: stable retrieval-unit id derived from document identity, parser version, parser profile, source file, section path, page range, start line, and text hash.
- `element_ids`: synthetic element ids for the content represented by the chunk. In Phase 1 this can be a one-item list derived from `chunk_id` or section/page identity.
- `page_start` / `page_end`: preserved for PDFs; empty or omitted for non-paged text unless a future parser can supply page mapping.
- `section_path`: list copy of `Chunk.path`.
- `asset_refs`: empty list in Phase 1.
- `parser_profile`: current parser profile, e.g. `markdown`, `txt`, `pdf:product_manual`, `pdf:generic`.
- `parser_version`: explicit small integer/string constant for lineage semantics.

## ID Strategy

- `node_id`: internal graph-local id, unchanged.
- `anchor_key`: existing compatibility anchor identity, unchanged.
- `chunk_identity_key`: existing rebuild reuse key, unchanged.
- `chunk_id`: new persistent external lineage id.

`chunk_id` should not use graph `node_id`. It should be deterministic from stable source and content inputs. It may be stored in graph node metadata and Qdrant payloads, but this task does not require Qdrant point ids to change.

## Data Flow

```text
parse_document()
  -> raw Chunk
  -> _with_lineage()
  -> post_process()
  -> build_graph()
  -> graph node metadata includes lineage
  -> storage/Qdrant payload mirrors metadata
```

Lineage should survive `_post_process` splitting and short-chunk merging. Split chunks should get distinct `chunk_id`s.

## Compatibility

- Existing `Result.to_dict()` remains additive via `metadata`.
- Existing tests expecting old fields should continue to pass.
- Incremental rebuild identity remains based on current `chunk_identity.py` until a later task explicitly migrates it.
- Parser profile changes already invalidate incremental identity via Phase 0 parser signature.

## Failure Behavior

- If `doc_id` cannot be inferred from metadata, use source file based fallback.
- If source file is empty, use a safe placeholder in the hash payload; do not expose raw absolute paths.
- If lineage generation fails unexpectedly, fail build clearly rather than silently writing partial corrupt lineage.
