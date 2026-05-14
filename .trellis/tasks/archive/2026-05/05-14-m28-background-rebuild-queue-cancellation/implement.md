# implement.md - M28 Background Rebuild Queue And Cancellation

## Implementation Checklist

- [x] Read backend specs with `trellis-before-dev` before coding.
- [x] Re-read M21, M26, and M27 task docs from archive.
- [x] Confirm whether M28 will implement durable SQLite queue in MVP or in-memory queue only.
- [x] Add queue config fields under `ManualLibraryConfig`:
  - `rebuild_queue_enabled`
  - `rebuild_queue_durable`
  - `rebuild_queue_max_workers`
  - `rebuild_queue_max_attempts`
  - `rebuild_queue_retry_backoff_seconds`
  - `rebuild_queue_history_limit`
- [x] Implement `RebuildJob` and queue status constants.
- [x] Implement `RebuildQueue` with:
  - enqueue
  - list
  - get
  - cancel
  - optional retry/requeue
  - coalescing/upgrading rules
  - deterministic synchronous test runner hook
- [x] Add optional SQLite queue store if included in MVP.
- [x] Wire queue into application state/lifespan so workers start once and shutdown cleanly.
- [x] Add cooperative cancellation fields/checkpoints to `RebuildTask`.
- [x] Update `start_library_rebuild()` to support queue-triggered execution without changing immediate mode.
- [x] Update upload/update/delete/bulk import trigger paths to enqueue when queueing is enabled.
- [x] Update `POST /manual-library/rebuild` response behavior for queued mode.
- [x] Add rebuild-job API endpoints:
  - list
  - inspect
  - cancel
  - optional retry
- [x] Add CLI commands for queued rebuild and rebuild-jobs list/inspect/cancel/retry.
- [x] Add retry classification helper and bounded backoff.
- [x] Ensure deterministic errors are not retried by default.
- [x] Keep all status payloads safe: no document text, vectors, credentials, signed URLs, request headers, raw stack traces, or high-cardinality payload dumps.
- [x] Update README with queue config, commands, recovery, and rollback.
- [x] Update backend specs if queue contracts become durable conventions.

Notes:

- M28 MVP intentionally shipped an in-process queue only. `rebuild_queue_durable` is a reserved config field; SQLite durable job recovery was not included because restart semantics need a separate persistence contract.
- CLI `manual-library rebuild --queued` runs the in-process queue to completion for local/scripted workflows. Server-side job list/inspect/cancel/retry is available through the API while the server process is alive.
- Backend specs did not require a durable queue convention update for this MVP; README documents process-local restart behavior and rollback.

## Suggested Implementation Phases

### Phase A - Contracts And Config

- Add config fields and env override tests.
- Add dataclasses/enums for job status and payload serialization.
- Add test-only fake executor hooks before threading complexity.

Validation:

```bash
uv run pytest tests/unit/test_config_env.py -q
```

### Phase B - In-Memory Queue Core

- Implement enqueue/list/get/cancel.
- Implement same-KB FIFO and duplicate coalescing.
- Implement synchronous drain method for tests.
- Keep queue disabled by default.

Validation:

```bash
uv run pytest tests/unit/test_rebuild_queue.py -q
```

### Phase C - Worker Execution And Cancellation

- Wire queue to `start_library_rebuild()`.
- Poll linked `RebuildTask` until terminal.
- Add cooperative cancellation checkpoints.
- Preserve old graph and dirty state for cancelled/failed jobs.

Validation:

```bash
uv run pytest tests/unit/test_manual_library.py -q
```

### Phase D - Retry Policy

- Classify retryable vs terminal errors.
- Add bounded attempts/backoff.
- Test S3/Qdrant/embedding-like transient failures with fakes.

Validation:

```bash
uv run pytest tests/unit/test_manual_blob_store.py tests/unit/test_manual_library.py -q
```

### Phase E - API And CLI

- Add job endpoints.
- Add CLI commands.
- Update upload/update/delete/bulk trigger paths to enqueue when enabled.
- Preserve immediate behavior when queue disabled.

Validation:

```bash
uv run pytest tests/unit/test_manual_library_api.py tests/unit/test_cli.py tests/unit/test_api.py -q
```

### Phase F - Durable Store And Docs

- If MVP includes durable queue, add SQLite schema and restart/abandoned job handling.
- Update README runbooks.
- Update specs if needed.

Validation:

```bash
uv run pytest tests/unit/test_rebuild_queue.py tests/unit/test_manual_registry.py -q
```

## Focused Tests To Add

- Queue disabled: `POST /manual-library/rebuild` still returns immediate task payload.
- Queue enabled: rebuild request returns queued job payload.
- Same-KB duplicate incremental requests coalesce.
- Same-KB full request upgrades queued incremental.
- Strict `allow_fallback=false` does not get weakened by coalescing.
- Different KBs can run concurrently when max workers permits.
- Same KB jobs run FIFO.
- Queued cancellation marks job cancelled and leaves dirty state pending.
- Running cancellation before swap preserves old graph and dirty state.
- Cancel request after swap can complete as succeeded with `cancel_requested=true`.
- Retryable S3/Qdrant/embedding failure retries until success or max attempts.
- Terminal invalid config/input error does not retry.
- Durable restart, if implemented: running jobs become abandoned/failed and queued jobs remain queued.
- API auth/scope checks for list/inspect/cancel.
- CLI JSON output for enqueue/list/inspect/cancel.

## Validation

Focused:

```bash
uv run pytest tests/unit/test_rebuild_queue.py -q
uv run pytest tests/unit/test_manual_library.py tests/unit/test_manual_library_api.py tests/unit/test_cli.py -q
uv run pytest tests/unit/test_api.py tests/unit/test_config_env.py -q
```

Full:

```bash
uv run pytest tests/ -q
```

## Review Gates

- Queue disabled remains the default.
- No external queue service is required.
- Same-KB rebuilds cannot overlap.
- Dirty state clears only after successful graph swap.
- Cancellation cannot leave partially swapped graph/vector/Qdrant state.
- Retry details are safe and bounded.
- Queue payloads do not leak raw document text, vectors, secrets, signed URLs, request headers, or raw stack traces.
- Existing M21 operations summaries still work for immediate and queued rebuilds.

## Rollback Points

- If durable queue storage is too risky, ship in-memory queue only and document restart behavior.
- If running cancellation proves unsafe, ship queued-job cancellation first and mark running cancellation as best-effort with limited checkpoints.
- If retry classification is too broad, default to manual retry and enable automatic retry only for clearly transient provider errors.
- If API compatibility gets noisy, keep `POST /manual-library/rebuild` immediate by default and require `queued=true` or config opt-in.
