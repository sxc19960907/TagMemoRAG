# design.md - M15 Qdrant Point-Level Incremental Updates

## Scope

M15 extends the Qdrant vector persistence backend so managed-library rebuilds can keep Qdrant collections aligned with the current built graph without rewriting or retaining unnecessary points. It builds on M14 identity and impact artifacts, but it must not change WAVE-RAG ranking or search execution.

## Current Data Flow

```text
build/rebuild
  -> GraphState(graph, vectors, meta)
  -> save_kb()
       -> graph.json
       -> selected vector store
       -> anchors.json
       -> meta.json

load_kb()
  -> graph.json + meta.json
  -> selected vector store load(node_ids)
  -> GraphState loaded into memory

search
  -> in-memory vectors + graph
  -> WAVE-RAG
```

This flow should remain intact. Qdrant is still persistence first, not the search-ranking engine.

## Proposed Contracts

### Vector Store API

Extend concrete Qdrant support around the existing `VectorStore` extension points:

```python
VectorStore.add(ids, vecs)        # existing full write/upsert path
VectorStore.delete(ids)           # delete explicit point ids
VectorStore.update(ids, vecs, payloads=None)  # upsert selected points
```

For NPZ, `add()` remains the full-file write path. `delete()` and `update()` may remain unsupported unless a later task needs them.

### Qdrant Payload

New points should use payload:

```json
{
  "kb_name": "default",
  "node_id": 12,
  "build_id": "202605...",
  "chunk_identity_key": "sha256:...",
  "manual_id": "cm1",
  "source_file": "coffee/cm1.md",
  "text_hash": "sha256:..."
}
```

`source_file` is useful for operator inspection, but must not become a metric label. Raw chunk text must never be stored in payload.

### Qdrant Sync Summary

Add an internal summary shape that can be embedded into task/meta/report metadata:

```json
{
  "provider": "qdrant",
  "strategy": "point_incremental",
  "points_upserted": 6,
  "points_deleted": 3,
  "points_reused": 120,
  "fallback_reason": ""
}
```

Fallback strategies:

- `point_incremental`: identity/impact data available and point diff is safe.
- `full_sync`: upsert all current graph points, then delete stale ids.
- `skipped`: provider is not Qdrant or rebuild is not managed-library.

## Incremental Sync Algorithm

Recommended safe flow for successful managed-library rebuilds:

```text
old_state + old chunk_identity + new_state + new chunk_identity + impact_report
  -> compute old node ids and new node ids
  -> compute stale ids = old node ids - new node ids
  -> compute new/changed ids from impact identity keys and graph node payloads
  -> qdrant.update(new_or_changed_ids, vectors, payloads)
  -> qdrant.delete(stale_ids)
  -> verify collection has all new graph node ids when practical
  -> save graph/meta/identity/report only if sync succeeds
```

The implementation should preserve the existing zero-downtime intent. A conservative ordering is acceptable:

1. Build `new_state` in memory.
2. Sync Qdrant into a state that can serve `new_state`.
3. Save graph/meta/anchors/identity/report.
4. Swap `AppState`.
5. Clear dirty state.

If step 2 fails, the old `AppState` remains active and dirty state remains pending. The old collection may have received partial upserts; this is acceptable only if old graph node ids remain loadable and no old points were deleted before the failure. For extra safety, delete stale points after all upserts succeed.

## Stale Point Cleanup

Primary MVP approach:

- Delete explicit stale node ids derived from `old_state.graph.nodes - new_state.graph.nodes`.
- For full rebuilds where node ids are reused but identities changed, upsert all current node ids so old vector contents are overwritten.
- For incremental point sync, upsert node ids associated with changed/new identities.

This avoids payload-filter delete complexity and is easy to test with fake clients. A future task can add build-id filter cleanup for orphaned points when old graph state is unavailable.

## Fallback Rules

Use full Qdrant sync when:

- old state is missing
- old chunk identity is missing or schema incompatible
- new graph cannot be mapped to identity keys
- impact report is absent or inconsistent
- fake/client capabilities do not support selective payload operations

Full sync means:

- upsert all current graph node vectors with current payloads
- delete explicit stale ids if old state is available
- report `strategy=full_sync` and a structured `fallback_reason`

Do not fall back silently.

## API / CLI Surface

No new endpoint is required for MVP. Existing surfaces should become more informative:

- `POST /manual-library/rebuild`
- `GET /rebuild/{task_id}`
- `python -m tagmemorag manual-library rebuild --kb default --mode incremental`

Responses may include additive metadata:

```json
{
  "qdrant_sync": {
    "provider": "qdrant",
    "strategy": "point_incremental",
    "points_upserted": 6,
    "points_deleted": 3,
    "points_reused": 120,
    "fallback_reason": ""
  }
}
```

## Rollout / Rollback

- `vector_store.provider=npz` remains unaffected.
- Operators can roll back behavior by using NPZ or by running `mode=full`; full Qdrant sync should still clean stale points.
- If point-level incremental sync is risky, ship full-sync cleanup first and report `strategy=full_sync` for all Qdrant rebuilds.
- Existing Qdrant collections without enriched payloads remain loadable because `load_kb()` still retrieves by graph node ids.

## Risks

- Node ids are rebuild-local. Identity must be used to decide changed/reused content, while node ids remain the Qdrant point ids for current graph compatibility.
- Partial Qdrant failures can leave extra points. The old graph must remain loadable, and stale deletion should happen late.
- Renames and parser config changes can make identity matching unsafe; prefer full sync in these cases.
