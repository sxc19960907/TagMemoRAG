# Code Context - M15 Qdrant Point-Level Incremental Updates

## Relevant Existing Modules

- `src/tagmemorag/storage/qdrant_vector.py`
  - Current Qdrant backend stores one point per graph node id.
  - Existing payload only includes `kb_name` and `node_id`.
  - `add()` currently upserts provided ids/vectors after ensuring the collection.
  - `load()` retrieves graph node ids with vectors and fails if any graph node vector is missing.
  - `search()` still loads all vectors and performs local dot-product ranking.

- `src/tagmemorag/storage/base.py`
  - `VectorStore` already has `delete()` and `update()` extension points that raise `NotImplementedError`.

- `src/tagmemorag/state.py`
  - `save_kb()` routes vector persistence through `_vector_store(...).add(...)`.
  - Managed-library rebuild now writes M14 identity and impact artifacts after successful rebuilds.

- `src/tagmemorag/chunk_identity.py`
  - Builds `data/{kb}/chunk_identity.json` with stable identity keys, text hashes, node ids, vector rows, and metadata hashes.

- `src/tagmemorag/rebuild_impact.py`
  - Builds non-textual impact summaries with added/removed/changed/reused/embedded counts.

## Key Constraints

- Qdrant point ids are current graph node ids, but node ids are rebuild-local.
- Identity keys and hashes should drive content-change decisions; node ids should drive current graph compatibility.
- Failed rebuilds must preserve currently served graph and dirty state.
- Search semantics should remain in-memory WAVE-RAG.
- Unit tests should use fake Qdrant clients, not a live service.
