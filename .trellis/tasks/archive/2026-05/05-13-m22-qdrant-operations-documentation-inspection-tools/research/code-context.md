# M22 Code Context

## Existing Qdrant Backend

- `src/tagmemorag/storage/qdrant_vector.py` defines `QdrantVectorStore`.
- Collection names are produced by `collection_name(prefix, kb_name)`, which normalizes unsafe characters and returns `{safe_prefix}_{safe_kb}`.
- Qdrant point ids are graph node ids.
- `QdrantVectorStore.load(ids)` retrieves vectors for graph node ids and raises `STORAGE_LOAD_FAILED` with `missing_count` and a capped `missing_node_ids` sample when vectors are missing.
- `QdrantVectorStore.search_candidates()` supports ANN preselection but search falls back to exact local scoring if ANN fails upstream.

## Payload Contract

- `_safe_payload()` allows only:
  - `kb_name`
  - `node_id`
  - `build_id`
  - `chunk_identity_key`
  - `manual_id`
  - `source_file`
  - `text_hash`
- `node_id` is converted to `int`; other safe values are stringified.
- Raw chunk text, vectors, secrets, and arbitrary payload fields are discarded.
- Legacy points with only `kb_name` and `node_id` remain load-compatible because vector loading does not require rich payload keys.

## Rebuild / Sync Behavior

- `src/tagmemorag/state.py` creates Qdrant stores through `_vector_store()`.
- `save_kb()` writes graph/anchor/meta artifacts locally and vectors to Qdrant when provider is `qdrant`.
- Managed-library rebuilds call `sync_qdrant_for_rebuild()` before metadata save and graph swap.
- Qdrant sync order is:
  1. upsert new/changed points
  2. refresh reused point payloads for safe incremental sync
  3. delete stale ids
- `QdrantSyncSummary` reports provider, strategy, points upserted/deleted/reused, and fallback reason.
- M21 adds `operations_summary` and `manual-library dirty` recovery actions that can be referenced from Qdrant docs.

## Batch Payload Context

- `QdrantVectorStore.update_payloads()` tries `batch_update_points()` first.
- If the client lacks batch support, it falls back to per-point `set_payload()`.
- Tests in `tests/unit/test_storage_state.py` and `tests/unit/test_manual_library.py` cover batch refresh and failure ordering.

## Existing Tests / Fake Client

- `tests/unit/test_storage_state.py` defines `FakeQdrantClient`.
- The fake client stores collections in memory and supports create, get, upsert, delete, set payload, batch payload update, retrieve, scroll, and search.
- Existing tests cover storage round trip, collection naming, missing vectors, ANN preselection, sync failures, payload refresh, and fallback behavior.
- M22 inspection tests should reuse or minimally extend this fake client.

## Likely Implementation Files

- `README.md`
- `src/tagmemorag/cli.py`
- `src/tagmemorag/storage/qdrant_vector.py`
- `src/tagmemorag/qdrant_ops.py` if a shared inspection helper is added
- `tests/unit/test_storage_state.py`
- `tests/unit/test_cli.py`

## Design Bias

Keep M22 operator-facing and read-only. Prefer documentation plus a compact CLI report over a broad API/admin UI. Do not mutate Qdrant from inspection, do not add live Qdrant to default CI, and do not expose raw vectors or document text.
