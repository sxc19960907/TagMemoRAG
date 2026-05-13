# M15 Qdrant Point-Level Incremental Updates

## Goal

Make managed-library rebuilds cheaper when `vector_store.provider=qdrant` by using M14 chunk identity and impact metadata to upsert only new/changed Qdrant points and remove stale points after disabled, deleted, split, merged, or changed manuals. The served WAVE-RAG graph should remain zero-downtime and ranking-compatible, while Qdrant collections stop accumulating obsolete vectors across incremental rebuilds.

## Background / Known Context

- M9 added Qdrant as a selectable vector persistence backend. It stores one point per graph node id in collection `{collection_prefix}_{kb_name}` and loads vectors back into memory for WAVE-RAG.
- M13 added managed-library rebuild modes `full`, `incremental`, and `auto`; full remains the compatibility default.
- M14 added `data/{kb}/chunk_identity.json`, `data/{kb}/rebuild_impact.json`, task-level `impact_summary`, chunk-level reuse inside dirty manuals, and dirty-state export.
- Current Qdrant persistence writes vectors through `VectorStore.add(ids, vecs)`. Existing behavior does not have explicit stale-point cleanup semantics.
- `VectorStore` already defines `delete()` and `update()` extension points that currently raise `NotImplementedError`.
- Search ranking should continue to use loaded graph/vector state and WAVE-RAG propagation. Remote ANN preselection is a separate post-v1 idea.

## Requirements

### 1. Qdrant Point Identity and Payload Contract

- Store enough payload on Qdrant points to identify the built KB state safely:
  - `kb_name`
  - `node_id`
  - `build_id`
  - `chunk_identity_key`
  - `manual_id`
  - `source_file` where safe and useful for operations
  - `text_hash` or equivalent non-textual chunk hash
- Do not store raw chunk text, API keys, or embeddings in payload beyond the vector itself.
- Preserve compatibility with older Qdrant collections that only have `kb_name` and `node_id` payloads.

### 2. Point-Level Cleanup on Successful Managed-Library Rebuilds

- After a successful managed-library rebuild with `vector_store.provider=qdrant`, remove points that are no longer present in the new built graph.
- Deleted, disabled, archived, renamed, split, and merged manuals must not leave stale points that can later be loaded or inspected as current.
- Cleanup must run only after the new graph/vector/meta artifacts have been built successfully, matching existing zero-downtime rebuild semantics.
- Failed rebuilds must leave the previous Qdrant collection and currently served graph usable.

### 3. Incremental Point Upsert

- For Qdrant-backed managed-library rebuilds, upsert only points whose vectors are new or changed where the M14 identity/impact data can prove the difference.
- Reused chunk identities should not require unnecessary Qdrant writes.
- If safe incremental point selection cannot be determined, fall back to full collection sync for the KB instead of risking missing vectors.
- Existing NPZ behavior remains unchanged.

### 4. Collection Consistency and Load Safety

- `load_kb()` must continue to fail clearly when graph nodes are missing Qdrant vectors.
- A successful save/sync should make the collection exactly represent the current graph node ids for that KB.
- Qdrant operations should use bounded, explicit ids where possible; avoid collection-wide destructive operations unless they are scoped to the KB collection and safe.
- Any Qdrant failure should be surfaced as structured project errors without leaking raw document text or sensitive config.

### 5. Operational Reporting

- Rebuild task metadata should report Qdrant sync outcome for managed-library rebuilds when Qdrant is enabled:
  - points upserted
  - points deleted
  - points reused/skipped
  - fallback reason if point-level sync degrades to full sync
- Persist the relevant summary in `meta.json` or `rebuild_impact.json` without raw text.
- Logs and metrics must avoid high-cardinality source paths as labels.

### 6. Compatibility and Safety

- Preserve default `vector_store.provider=npz` behavior.
- Preserve WAVE-RAG ranking, graph topology, anchor behavior, and existing API response shapes except additive metadata.
- Continue supporting old KBs without `chunk_identity.json` or enriched Qdrant payloads.
- Do not introduce a live Qdrant dependency into the default test suite; use fake clients for unit coverage.

## Acceptance Criteria

- [ ] Qdrant point payload includes safe chunk/build identity fields for newly saved points.
- [ ] Successful Qdrant-backed managed-library rebuild deletes stale points that no longer exist in the current graph.
- [ ] Incremental Qdrant sync upserts only new/changed points when identity/impact data is available.
- [ ] Unsafe or missing identity/impact cases fall back to full Qdrant sync with structured reason metadata.
- [ ] NPZ save/load/rebuild behavior remains unchanged.
- [ ] `load_kb()` still detects and reports missing Qdrant vectors for graph nodes.
- [ ] Rebuild task metadata includes Qdrant sync counts for Qdrant-backed library rebuilds.
- [ ] Failed rebuilds preserve the old graph and do not clear dirty state.
- [ ] Tests cover fake-client Qdrant upsert/delete behavior, stale cleanup, fallback sync, metadata reporting, and NPZ regression.
- [ ] README/backend spec document Qdrant point-level sync semantics and rollback behavior.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- Focused Qdrant storage and managed-library rebuild tests pass.
- `uv run pytest tests/ -q` passes.
- Durable payload/report contracts are documented in README and backend spec.
- No raw manual text, vectors, API keys, or high-cardinality values are added to metrics labels.

## Out of Scope

- Remote ANN preselection for `/search`.
- Changing WAVE-RAG ranking, graph edge semantics, or result ordering.
- Distributed rebuild coordination or multi-replica cache invalidation.
- Database-backed rebuild audit history.
- Qdrant Cloud API key/config expansion unless required by tests for this task.
- Live Qdrant integration tests in the default test suite.

## Open Questions

- Should stale cleanup use explicit node-id deletion from the new graph diff, or payload-filter deletion by `build_id != current` after successful upsert?
- Should point-level sync counts live only in task/meta/report metadata, or also expose a dedicated Qdrant sync artifact under `data/{kb}/`?
