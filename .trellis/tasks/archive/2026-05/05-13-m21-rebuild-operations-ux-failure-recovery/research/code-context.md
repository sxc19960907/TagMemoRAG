# M21 Code Context

## Existing Rebuild State

- `src/tagmemorag/state.py` defines `RebuildTask` and `RebuildTask.to_dict()`.
- Current task fields include status, requested/effective mode, dirty manual count, fallback reasons, reused/embedded chunk counts, impact summary, and Qdrant sync summary.
- `AppState.start_rebuild()` stores rebuild tasks in memory only.
- `start_library_rebuild()` passes an `on_success` callback that clears pending manifest state after successful save/swap.
- Failed rebuilds set `task.status="failed"` and `task.error`, then leave old graph in place.

## Existing Manual-Library Inspection

- `src/tagmemorag/manual_library.py` stores `.tagmemorag-library.json` with `pending_changes` and `dirty_manuals`.
- `export_dirty_state()` returns dirty manual rows with manual id, source file, operation, updated time, checksum, status, searchable, and exists.
- `GET /manual-library` returns pending changes, dirty count, dirty manuals, and manual records.
- `GET /manual-library/dirty` returns JSON or CSV dirty state.
- `python -m tagmemorag manual-library dirty` mirrors dirty export in CLI.

## Existing Qdrant Recovery-Sensitive Behavior

- `sync_qdrant_for_rebuild()` upserts new/changed vectors, refreshes reused point payloads for incremental sync, then deletes stale ids.
- `QdrantSyncSummary` reports strategy, points upserted/deleted/reused, and fallback reason.
- `tests/unit/test_manual_library.py` includes tests for:
  - failed library rebuild keeps old graph and pending marker
  - full Qdrant sync deletes stale points
  - incremental sync skips reusable points
  - incremental sync batches reused payload refresh
  - incremental rebuild followed by ANN search regression
  - fallback to full sync without chunk identity
  - failed Qdrant sync keeps pending dirty state
  - failed reused payload refresh blocks stale delete and graph swap

## Likely Implementation Files

- `src/tagmemorag/state.py`
- `src/tagmemorag/manual_library.py`
- `src/tagmemorag/api.py`
- `src/tagmemorag/cli.py`
- `README.md`
- `tests/unit/test_manual_library.py`
- `tests/unit/test_manual_library_api.py`
- `tests/unit/test_cli.py`
- `tests/unit/test_api.py`

## Design Bias

M21 should improve status composition and recovery guidance around existing contracts. Avoid durable task history, external queues, or schema-heavy new persistence unless a future task explicitly expands the operations model.
