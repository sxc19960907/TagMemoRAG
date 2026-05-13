# design.md - M9 Qdrant Vector Backend

## Scope

Add Qdrant as a selectable vector persistence backend. The MVP keeps WAVE-RAG's in-memory matrix and graph propagation unchanged:

```text
build_kb() -> GraphState(vectors in memory)
save_kb() -> graph/meta/anchors local files + selected vector backend
load_kb() -> graph/meta/anchors local files + selected vector backend loaded into memory
```

## Config

```yaml
vector_store:
  provider: npz
  qdrant_url: http://localhost:6333
  collection_prefix: tagmemorag
  timeout_seconds: 10
```

`provider=npz` is the default. `provider=qdrant` uses collection name `{collection_prefix}_{kb_name}` with unsafe characters normalized.

## Storage Contract

- NPZ remains `data/{kb_name}/vectors.npz`.
- Qdrant stores one point per graph node.
- Point id is the integer node id.
- Vector is the embedding row.
- Payload includes `kb_name` and `node_id` for inspection and future filters.
- Loading retrieves all point ids from the graph and returns vectors ordered by node id.

## Error Handling

- Missing `qdrant-client` import -> `INVALID_CONFIG`.
- Qdrant operation failure -> `STORAGE_LOAD_FAILED` with safe detail.
- Missing vector for a graph node -> `STORAGE_LOAD_FAILED`.
- Dimension mismatch -> `STORAGE_SCHEMA_MISMATCH` or `STORAGE_LOAD_FAILED` depending on load context.

## Deferred

- Remote ANN pre-selection for `/search`.
- Payload filters in Qdrant.
- Incremental upsert/delete during manual update.
- Qdrant Cloud API key support.
