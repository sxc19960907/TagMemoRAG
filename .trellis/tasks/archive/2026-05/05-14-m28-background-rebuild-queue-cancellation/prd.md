# M28 Background Rebuild Queue And Cancellation

## Goal

Add a background managed-library rebuild queue with cancellation, retry, duplicate rebuild coalescing, and operator-visible job status. M28 should decouple upload/update/delete API requests from immediate long-running rebuild execution while preserving the existing safety guarantees: old graphs keep serving during failures, dirty state clears only after a successful graph swap, and object-storage/Qdrant failures remain recoverable.

## Background / Known Context

- M21 added rebuild operations summaries, dirty-state inspection, and recovery guidance, but explicitly avoided a queue or durable history.
- M26 added a SQLite manual registry, local blob store, registry-backed rebuild staging, and audit events.
- M27 added S3-compatible blob storage behind `ManualBlobStore`; failed S3 reads during staging can make rebuilds fail before graph build begins.
- Current `start_library_rebuild()` starts work immediately through an in-memory thread and rejects concurrent rebuilds with `REBUILD_IN_PROGRESS`.
- `POST /manual-library/rebuild` returns a current-process task id but no queue position, cancellation handle, retry policy, or durable history.
- Upload/update/delete APIs can still trigger a rebuild directly, which is convenient locally but awkward when several operators or bulk imports create repeated rebuild requests.
- Dirty state is already the source of truth for "what needs rebuilding"; queue jobs should point at a KB and rebuild mode rather than copying raw manual content.

## Problem

Production deployments need rebuild orchestration that is more forgiving than "start now or fail":

- Bulk imports and repeated uploads can create several rebuild requests for the same KB in a short window.
- Object storage, Qdrant, and HTTP embedding providers can fail transiently and should support bounded retry without manual polling loops.
- Operators need to cancel queued or running rebuilds when a higher-priority full rebuild, rollback, or maintenance window supersedes the current work.
- API clients need a stable way to ask for a rebuild and receive a queued job response instead of blocking on immediate execution or handling `REBUILD_IN_PROGRESS`.
- Multi-KB deployments need per-KB ordering while still allowing independent KB rebuilds to progress.

## Requirements

### 1. Queue Semantics

- Add a managed-library rebuild queue for requests from:
  - `POST /manual-library/rebuild`
  - upload/update/delete endpoints when `trigger_rebuild=true`
  - bulk import when rebuild is requested
  - CLI `manual-library rebuild`
- Jobs must include safe fields:
  - `job_id`
  - `kb_name`
  - requested `mode`: `full | incremental | auto`
  - `allow_fallback`
  - `status`: `queued | running | cancel_requested | cancelled | succeeded | failed | retrying`
  - queue position or ordering timestamp
  - linked rebuild `task_id` when work starts
  - attempt count and max attempts
  - safe error/recovery summary
- Queue processing should be FIFO per KB.
- Independent KBs may run concurrently up to a configured worker limit, but only one rebuild for the same KB may be running at a time.
- Local/default deployments should remain simple: no external queue service is required.

### 2. Duplicate Rebuild Coalescing

- If a rebuild is already queued or running for the same KB, new compatible requests should coalesce rather than create unbounded duplicate jobs.
- Coalescing rules should be explicit:
  - `full` supersedes `incremental` and `auto`.
  - `incremental` may merge with queued `incremental` or `auto` if dirty state remains pending.
  - `allow_fallback=false` should not be silently merged into a looser job unless the stricter semantics are preserved.
  - A request for a different KB must not coalesce with the current KB.
- Coalesced responses should identify the existing or upgraded job and include a `coalesced=true` flag.

### 3. Cancellation

- Add cancellation for queued jobs.
- Running job cancellation should be cooperative and best-effort:
  - safe cancellation points before staging, before embedding/build, before Qdrant sync, and before graph swap are acceptable for MVP.
  - cancellation must not interrupt an atomic graph/vector save, Qdrant sync critical section, or dirty-state clearing in a way that leaves inconsistent state.
- Cancelling a running rebuild must preserve the old graph and leave dirty state pending.
- Cancelled jobs should remain visible in current-process/durable history long enough for operators to inspect outcome.
- Cancellation must be authorized with rebuild/admin scope consistent with existing auth patterns.

### 4. Retry Policy

- Add bounded retry for transient rebuild failures:
  - object-storage read/load failures
  - embedding provider transient failures
  - Qdrant connectivity/sync failures
  - staging temp directory cleanup race or filesystem transient failures when safe
- Do not retry deterministic input/config errors by default:
  - invalid metadata
  - unsupported source suffix
  - unsafe paths/blob keys
  - missing required config or credentials
  - schema mismatch
- Retry policy should be configurable:
  - `manual_library.rebuild_queue_enabled`
  - `manual_library.rebuild_queue_max_workers`
  - `manual_library.rebuild_queue_max_attempts`
  - `manual_library.rebuild_queue_retry_backoff_seconds`
  - `manual_library.rebuild_queue_history_limit`
- Retry metadata must be safe: attempt count, next retry time, error code/class, recovery hint. Do not store raw stack traces, document text, vectors, credentials, signed URLs, or request headers.

### 5. Persistence And Recovery

- MVP may use SQLite when `manual_library.registry_backend=sqlite` because M26 already introduced SQLite; file-sidecar mode may fall back to in-memory queue if durable queue persistence is too risky.
- If durable queue storage is implemented, restart behavior must be explicit:
  - queued jobs can resume as queued.
  - running jobs from a dead process become `failed` or `abandoned` with safe detail.
  - dirty state remains the rebuild truth and must not be cleared by queue recovery alone.
- Queue schema must be small and migration-safe. Do not store raw manual bytes, raw metadata JSON beyond safe request fields, vectors, or large exception traces in queue rows.

### 6. API And CLI

- `POST /manual-library/rebuild` should return a queue job response when queueing is enabled, with status code `202`.
- Add job inspection and cancellation endpoints, for example:
  - `GET /manual-library/rebuild-jobs?kb_name=default&status=...`
  - `GET /manual-library/rebuild-jobs/{job_id}`
  - `POST /manual-library/rebuild-jobs/{job_id}/cancel`
  - `POST /manual-library/rebuild-jobs/{job_id}/retry` for failed jobs if manual retry is useful
- Preserve `GET /rebuild/{task_id}` for low-level current-process task inspection.
- CLI should expose scriptable commands:
  - `manual-library rebuild --queued`
  - `manual-library rebuild-jobs list`
  - `manual-library rebuild-jobs inspect --job-id ...`
  - `manual-library rebuild-jobs cancel --job-id ...`
  - optional `manual-library rebuild-jobs retry --job-id ...`
- Default CLI output should remain JSON for automation.

### 7. Safety And Compatibility

- Existing immediate rebuild behavior should remain available when queueing is disabled.
- Existing default tests should not require a running external queue, Redis, Celery, MinIO, Qdrant, or network access.
- Failed or cancelled queued rebuilds must preserve old `GraphState` and dirty state.
- Queue status and logs must not expose raw document bodies, chunk text, vectors, credentials, full local absolute paths where avoidable, signed URLs, or high-cardinality payload dumps.
- Search and ranking semantics are out of scope.

### 8. Documentation

- README should include:
  - when to enable queued rebuilds
  - queue config fields
  - examples for queued rebuild, inspect, cancel, and retry
  - recovery guidance for abandoned/running-at-restart jobs
  - rollback to immediate rebuild behavior

## Acceptance Criteria

- [ ] A Trellis design exists for queue state, coalescing, cancellation, retry classification, persistence, API/CLI contracts, observability, rollout, and rollback.
- [ ] Queueing can be enabled without changing manual upload/update/delete API semantics beyond returning safe job metadata.
- [ ] Concurrent rebuild requests for the same KB are queued or coalesced instead of failing with `REBUILD_IN_PROGRESS`.
- [ ] Independent KB rebuilds can run concurrently when configured, while same-KB rebuilds remain ordered.
- [ ] Queued jobs can be cancelled before they start.
- [ ] Running jobs support cooperative cancellation at safe checkpoints and preserve old graph plus pending dirty state.
- [ ] Transient S3/Qdrant/embedding failures can retry with bounded attempts and safe status details.
- [ ] Deterministic config/input errors are not retried by default.
- [ ] API and CLI provide list/inspect/cancel flows with JSON output and no unsafe payloads.
- [ ] Dirty state still clears only after a successful graph swap.
- [ ] Existing immediate rebuild mode remains available and tested.
- [ ] Focused tests cover queue ordering, coalescing, cancellation, retry, restart recovery if durable storage is implemented, and old-graph safety.
- [ ] `uv run pytest tests/ -q` passes.

## Definition Of Done

- PRD, design, implementation plan, and context manifests are complete before implementation starts.
- Implementation follows existing `AppState`, `RebuildTask`, `manual_library`, registry/blob-store, and operations-summary contracts.
- Unit tests use fake queue workers and fake S3/Qdrant/embedding failures; default tests remain offline.
- Documentation includes operational examples and rollback guidance.
- Specs are updated if queue contracts become durable backend conventions.

## Out Of Scope For M28 MVP

- External distributed queues such as Redis, Celery, SQS, Kafka, or database advisory locks.
- True hard thread cancellation or killing arbitrary Python execution.
- Multi-replica leader election or exactly-once processing.
- Cron/scheduled rebuilds.
- Admin UI queue dashboard; M29 can surface the queue visually.
- Import/export bundle queueing; M30 owns bundle workflows.
- Provider-specific retry policy tuning beyond safe generic transient classification.

## Research References

- `.trellis/workspace/suixingchen/roadmap.md`
- `.trellis/tasks/archive/2026-05/05-13-m21-rebuild-operations-ux-failure-recovery/`
- `.trellis/tasks/archive/2026-05/05-14-m26-manual-registry-blob-storage/`
- `.trellis/tasks/archive/2026-05/05-14-m27-s3-compatible-blob-store/`
- `src/tagmemorag/state.py`
- `src/tagmemorag/manual_library.py`
- `src/tagmemorag/manual_registry.py`
- `src/tagmemorag/manual_blob_store.py`
- `src/tagmemorag/api.py`
- `src/tagmemorag/cli.py`
- `tests/unit/test_manual_library.py`
- `tests/unit/test_manual_library_api.py`
- `tests/unit/test_cli.py`
