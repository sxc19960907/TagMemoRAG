# M13 Code Context

## Existing Rebuild Flow

- `src/tagmemorag/state.py` owns `AppState.start_rebuild()`, `_rebuild_worker()`, `build_kb()`, `save_kb()`, `load_kb()`, and `start_library_rebuild()`.
- `build_kb()` currently scans every supported document under `docs_dir`, loads metadata with `load_manual_metadata()`, skips inactive statuses via `is_active_status()`, parses all chunks, embeds all text with `embedder.encode_batch()`, calls `build_graph()`, reconciles anchors, and returns a new `GraphState`.
- `_rebuild_worker()` already preserves double-buffer behavior: it only calls `save_kb()` and `swap_kb()` after `build_kb()` succeeds. Failures mark the task failed and keep the old graph.
- `start_library_rebuild()` resolves `manual_library.library_root(kb_name, cfg)` and clears the pending manifest only in the `on_success` callback.

## Manual Library State

- `src/tagmemorag/manual_library.py` has a per-KB `.tagmemorag-library.json` manifest with `pending_changes`, `last_successful_build_id`, and `updated_at`.
- Mutations currently call `mark_pending(kb_name, cfg, pending=True)` but do not record which manual changed.
- The managed record list can compute `chunk_count` and `searchable` from a loaded `GraphState` by matching metadata `manual_id`.
- `delete_manual()` removes source and sidecar and then marks pending, so dirty tracking for hard delete must capture the manual ID/source before deletion.

## Graph and Vector Persistence

- `src/tagmemorag/graph_builder.py` builds a complete graph from a complete chunk list and embedding matrix. Cross-manual semantic edges are possible because it computes `embeddings @ embeddings.T` globally.
- `JsonGraphStore` only saves/loads full graphs.
- `NpzVectorStore.add()` writes the full IDs/vector matrix to `vectors.npz`.
- `QdrantVectorStore.add()` upserts provided vectors. `load(ids)` retrieves only requested graph node IDs, so stale old Qdrant points may not affect correctness, but search/load-all behavior should be reviewed if stale points remain.

## API/UI/CLI Integration Points

- `api.ManualLibraryRebuildRequest` currently only has `kb_name`.
- `POST /manual-library/rebuild` requires `rebuild` scope and calls `start_library_rebuild(app_state, request.kb_name, settings, embedder=embedder)`.
- Manual library admin UI uses `manual_library.html` and `manual_library.js`; rebuild controls already exist and can be extended with a mode selector.
- CLI currently has no `manual-library rebuild` command group. Existing command groups show JSON output patterns (`manual-bulk`, `tag`, `feedback`).

## Design Implications

- M13 should add dirty state first, because existing full rebuild can ignore it safely.
- Incremental rebuild should not patch graph edges locally; it should rebuild graph topology globally from final chunks/vectors to preserve full-build semantics.
- MVP can optimize embedding only and still save full final artifacts. This is a conservative path that fits current storage contracts.
- Fallback full rebuild is needed when old state or dirty state is unavailable, especially for old manifests with only `pending_changes=true`.
