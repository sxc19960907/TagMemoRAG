# Code Context - M28 Background Rebuild Queue And Cancellation

## Existing Rebuild Entry Points

- `src/tagmemorag/state.py`
  - `RebuildTask` is the current in-memory task payload.
  - `AppState.rebuild_tasks` is process-local.
  - `AppState.start_rebuild()` acquires a per-KB lock and starts a worker thread immediately.
  - `_rebuild_worker()` owns build, save, Qdrant sync, graph swap, task status, metrics, and cleanup.
  - `start_library_rebuild()` wraps managed-library rebuilds and registry staging.

- `src/tagmemorag/api.py`
  - `POST /manual-library/rebuild` calls `start_library_rebuild()` directly and returns `task.to_dict()`.
  - `GET /rebuild/{task_id}` reads `app_state.rebuild_tasks`.
  - upload/update/delete/bulk import paths can trigger rebuild directly.

- `src/tagmemorag/cli.py`
  - `manual-library rebuild` starts a rebuild and polls until terminal status.
  - `manual-library dirty` exposes pending/recovery state.

## Existing Safety Contracts

- Dirty state clears only through the rebuild success path after graph swap.
- Failed rebuilds preserve old `GraphState`.
- Registry-backed rebuilds materialize active registry records into a temporary sidecar tree.
- S3 blob read failure maps to a failed task and leaves dirty state pending.
- Qdrant sync happens before graph/meta save; stale deletes run only after required upserts/reused payload refreshes.

## Useful Tests To Read Before Implementation

- `tests/unit/test_manual_library.py`
  - failed rebuild pending state
  - incremental/full/auto behavior
  - Qdrant sync failure safety
  - registry/S3 rebuild failure safety

- `tests/unit/test_manual_library_api.py`
  - API dirty/rebuild surfaces

- `tests/unit/test_cli.py`
  - CLI manual-library rebuild/registry command shapes

- `tests/unit/test_manual_blob_store.py`
  - S3 fake-client failure behavior

## Recommended Implementation Shape

- Keep queue orchestration separate from build logic.
- Add a queue object to `AppState` or API startup state, but keep immediate rebuild mode available.
- Prefer a deterministic queue executor interface for tests so unit tests do not rely on timing.
- If SQLite persistence is added, store only safe job metadata and treat dirty state as the rebuild truth after restart.

## Main Risks

- Running cancellation can be unsafe if it interrupts Qdrant sync or graph save. Use cooperative checkpoints only.
- Coalescing can accidentally weaken strict rebuild requests. Preserve `allow_fallback=false` semantics.
- Retrying deterministic config/input failures can hide operator errors. Keep retry classification conservative.
- Queue persistence can imply stronger guarantees than the app can provide in a single-process MVP. Document restart behavior precisely.
