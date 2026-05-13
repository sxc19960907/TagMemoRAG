# M13 Incremental Manual Rebuild/Update Path

## Goal

Make managed manual updates cheaper and safer by adding an incremental rebuild path for `product_manuals/{kb_name}`. M13 should let operators update, replace, disable, delete, or bulk-import manuals and then rebuild only the affected manual chunks while preserving the existing zero-downtime serving contract. The outcome is faster production iteration, less embedding work, and a foundation for larger manual libraries without changing WAVE-RAG search semantics.

## Background / Known Context

- M0 introduced full KB build/load/save, WAVE-RAG graph search, anchors, `GraphState`, FastAPI, CLI, and zero-downtime asynchronous rebuild.
- M3 introduced deterministic eval suites and CLI regression gates.
- M5-M8 introduced manual metadata, filters/facets, managed manual library operations, admin UI, and tag suggestions.
- M9 added Qdrant as a selectable vector persistence backend, but WAVE-RAG still loads vectors into memory for graph propagation.
- M10-M12 added bulk import, tag governance, search feedback capture, eval promotion, and a larger checked-in eval fixture.
- Current `build_kb()` scans every active document, parses all chunks, embeds all text, rebuilds the entire graph, reconciles anchors, and writes `graph.json`, `vectors.npz` or Qdrant vectors, `anchors.json`, and `meta.json`.
- Current managed-library mutations mark a single KB-level `pending_changes=true` manifest flag. The manifest does not record which manuals changed.
- Current `start_library_rebuild()` always performs a full rebuild from `manual_library.root_dir/{kb_name}` and clears pending only after success.
- Current vector store interfaces define `delete()` and `update()` placeholders but only `add()` is implemented for NPZ and Qdrant.

## Assumptions

- M13 remains file-backed and does not introduce a database registry.
- Incremental rebuild is advisory but should be exact enough that the final saved graph and vectors are equivalent to a full rebuild for supported edits.
- The MVP can still save a full `graph.json` and full in-memory vector matrix after an incremental build. The key win is avoiding parsing/embedding unchanged manuals, not necessarily partial persistence writes.
- Node IDs are rebuild-local and may change after incremental rebuild. Stable identity remains `anchor_key`, `source_file`, metadata, and manual IDs.
- Semantic edges may cross manual boundaries, so changed manuals can affect edges connected to unchanged nodes. M13 must recompute graph edges globally or otherwise prove equivalence for cross-manual edges.
- For Qdrant MVP, it is acceptable to rewrite/upsert the full final vector set after an incremental merge unless doing safe point deletion/update is straightforward and tested.
- Bulk import can mark many manual IDs as dirty. If too many manuals are dirty, the implementation may fall back to full rebuild.

## Requirements

### 1. Dirty Manual Tracking

- Extend managed manual mutations to record which `manual_id` and `source_file` changed.
- Track operation type where useful: `upsert`, `metadata_update`, `file_replace`, `disable`, `archive`, `hard_delete`, `bulk_import`.
- Store dirty state under the existing per-KB manifest or a companion file under the managed library root.
- Preserve backward compatibility with existing manifests that only have `pending_changes`.
- Ensure dirty state writes are atomic and path-safe.
- Clear dirty state only after a successful rebuild that includes those changes.

### 2. Incremental Rebuild Service

- Add a backend service path that accepts a KB and a set of dirty manual IDs or derives them from the manifest.
- Load the currently served or persisted `GraphState` as the base.
- Reuse chunks and vectors for unchanged active manuals when their metadata/content identity still matches the current graph.
- Parse and embed only dirty active manuals.
- Remove chunks for disabled, archived, or hard-deleted dirty manuals.
- Recompute graph topology for the final chunk set so semantic, consecutive, parent-child, and sibling edges match full-build semantics.
- Reconcile anchors against the final graph using existing `JsonAnchorStore.reconcile()` behavior.
- Save resulting KB artifacts through existing `save_kb()` semantics.

### 3. Equivalence and Fallback

- Provide a deterministic comparison test that proves incremental rebuild results are equivalent to a full rebuild for representative cases:
  - metadata-only update
  - source file replacement
  - create new manual
  - disable/delete manual
  - bulk import with multiple updates
- If a safe incremental base is unavailable, corrupted, schema-incompatible, missing vectors, or the dirty set cannot be resolved, fall back to full rebuild.
- Include the chosen mode and fallback reason in task/result metadata.
- Do not mutate the currently served graph until the new state is fully built and saved.

### 4. API and CLI Controls

- Extend library rebuild API to support mode selection:
  - `mode="full"` for existing behavior
  - `mode="incremental"` for strict incremental with fallback allowed by default
  - optionally `mode="auto"` as the default future behavior if safe
- Return task metadata including `requested_mode`, `effective_mode`, `dirty_manual_count`, and `fallback_reason`.
- Add CLI support for managed library rebuild mode if the CLI currently exposes or should expose the managed rebuild workflow.
- Keep existing `/rebuild {docs_dir,kb_name}` backward compatible and full-build oriented.

### 5. Admin UI Integration

- Add controls to the existing manual library admin UI for full vs incremental rebuild.
- Show whether a KB has dirty manuals and, if available, which manuals are dirty.
- Keep the UI operational and dense; avoid adding a separate page unless necessary.
- Preserve existing upload/edit/bulk/tag governance flows.

### 6. Cache, Search, and Feedback Compatibility

- Ensure successful incremental rebuild invalidates or isolates query cache entries for the rebuilt KB exactly like full rebuild.
- Ensure `/search` responses continue to include current `build_id`, `trace_id`, and `search_id`.
- Ensure M12 feedback records and eval promotion remain valid; promoted eval drafts should be runnable against incrementally rebuilt KBs.
- Do not change WAVE-RAG ranking behavior except as required by updated manual content/metadata.

### 7. Observability and Safety

- Log safe low-cardinality fields only: `kb_name`, requested/effective mode, counts, duration, fallback reason code, trace/task ID.
- Do not log raw document text, full filenames as metrics labels, API keys, vectors, or notes.
- Extend rebuild metrics if needed with allowed labels only (`operation`, `outcome`, `kb_name`).
- Preserve double-buffer behavior: failed incremental rebuilds keep old graph, old cache safety, dirty state, and pending manifest.

### 8. Documentation

- Update README with full vs incremental rebuild behavior, API/CLI examples, and fallback semantics.
- Update backend specs if M13 introduces durable conventions around dirty tracking, incremental graph assembly, vector store update/delete semantics, or rebuild task metadata.

## Acceptance Criteria

- [ ] Manual library mutations record dirty manual information in a durable per-KB file/manifest.
- [ ] Operators can request an incremental managed-library rebuild through API and CLI.
- [ ] Incremental rebuild reuses unchanged manual embeddings and only parses/embeds dirty active manuals in normal cases.
- [ ] Incremental rebuild removes disabled/archived/deleted manuals from the final graph.
- [ ] The final graph/vectors/search behavior match a full rebuild for tested scenarios.
- [ ] Unsafe or unsupported incremental situations fall back to full rebuild with a structured fallback reason.
- [ ] Successful incremental rebuild clears pending/dirty state only after graph swap and save succeed.
- [ ] Failed incremental rebuild preserves the old served `GraphState` and leaves pending/dirty state visible.
- [ ] Query cache behavior remains correct after incremental rebuild.
- [ ] Auth scopes and KB allowlists remain enforced for all rebuild/mutation operations.
- [ ] Admin UI exposes incremental/full rebuild controls and dirty state.
- [ ] Tests cover dirty tracking, service merge behavior, API/CLI mode selection, fallback paths, cache behavior, Qdrant/NPZ persistence expectations, and eval fixture compatibility.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- Unit/API/CLI/UI/eval tests cover the incremental workflow.
- `uv run pytest tests/ -q` passes.
- Documentation explains when to use incremental vs full rebuild and how fallback works.
- Any durable backend conventions learned during implementation are added to `.trellis/spec/backend/`.

## Out of Scope

- Database-backed change journal or audit history.
- Cross-process distributed rebuild coordination.
- Multi-replica cache invalidation beyond current single-process cache behavior.
- Remote ANN preselection or changing WAVE-RAG ranking.
- Partial graph persistence format that writes only changed graph nodes/edges.
- True Qdrant point-level garbage collection if full final upsert/rewrite is safer for MVP.
- Background file watchers or automatic scheduled rebuilds.
- Manual diff visualization in the admin UI.

## Follow-Up Ideas

- Persistent chunk identity map keyed by `(manual_id, source_file, header/path, text hash)` for even stronger reuse.
- Threshold-based auto mode: incremental below N dirty manuals, full rebuild above N.
- Rebuild impact report showing added/removed/changed chunks.
- CSV or API export of dirty manual state.
- Qdrant point-level delete/update optimization after MVP semantics are stable.
