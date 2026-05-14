# design.md - M28 Background Rebuild Queue And Cancellation

## Scope

M28 adds orchestration around managed-library rebuilds. It should not rewrite parsing, graph building, vector storage, Qdrant sync, S3 blob storage, search ranking, or admin UI. The queue owns rebuild request lifecycle; `AppState.start_rebuild()` still owns the actual build/swap worker.

The design should preserve two existing truths:

1. Dirty state is the source of truth for pending manual-library changes.
2. The loaded `GraphState` is replaced only after a successful rebuild save/swap.

## Current Flow

```text
POST /manual-library/rebuild
  -> start_library_rebuild(app_state, kb, cfg, mode, allow_fallback)
     -> materialize registry staging if enabled
     -> app_state.start_rebuild()
        -> create RebuildTask(status=running)
        -> launch worker thread immediately
        -> worker builds/saves/syncs/swaps
        -> on_success clears dirty manifest
```

If a same-KB rebuild is already running, `AppState.start_rebuild()` raises `REBUILD_IN_PROGRESS`.

## Target Architecture

```text
API / CLI / upload trigger
  -> RebuildQueue.enqueue(kb, mode, allow_fallback, trigger)
       -> coalesce or create RebuildJob
       -> persist job if durable queue is enabled
       -> return job payload

RebuildQueue worker loop
  -> pick next runnable job per KB and worker limit
  -> mark running
  -> call start_library_rebuild(...)
  -> wait for RebuildTask terminal status
  -> retry / succeed / fail / cancel
```

The queue is an orchestration layer. It should not duplicate build logic, materialize registry sources itself, or clear dirty state directly.

## Proposed Modules

- `src/tagmemorag/rebuild_queue.py`
  - `RebuildJob` dataclass.
  - `RebuildQueue` in-memory orchestrator.
  - coalescing and cancellation logic.
  - retry classification helpers.

- `src/tagmemorag/rebuild_queue_store.py` or nested implementation
  - optional SQLite persistence for registry-backed deployments.
  - small schema and migration helpers.

- `src/tagmemorag/state.py`
  - add cooperative cancellation hooks to `RebuildTask` and worker checkpoints.
  - keep immediate rebuild path available.

- `src/tagmemorag/api.py`
  - queue-aware `POST /manual-library/rebuild`.
  - job list/inspect/cancel endpoints.

- `src/tagmemorag/cli.py`
  - queued rebuild and rebuild-jobs commands.

## Data Model

### RebuildJob

```python
@dataclass
class RebuildJob:
    job_id: str
    kb_name: str
    requested_mode: str
    effective_mode: str
    allow_fallback: bool
    status: str
    trigger: str
    priority: int
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    coalesced_into: str | None = None
    task_id: str | None = None
    attempt: int = 0
    max_attempts: int = 1
    next_run_at: str | None = None
    cancel_requested: bool = False
    error: dict | None = None
    operations_summary: dict | None = None
```

Recommended statuses:

- `queued`
- `running`
- `retrying`
- `cancel_requested`
- `cancelled`
- `succeeded`
- `failed`
- `abandoned`

Safe `trigger` values:

- `api`
- `cli`
- `upload`
- `file_replace`
- `metadata_update`
- `delete`
- `bulk_import`

### SQLite Schema If Durable Queue Is Implemented

```sql
manual_rebuild_jobs(
  job_id TEXT PRIMARY KEY,
  kb_name TEXT NOT NULL,
  requested_mode TEXT NOT NULL,
  effective_mode TEXT NOT NULL,
  allow_fallback INTEGER NOT NULL,
  status TEXT NOT NULL,
  trigger TEXT NOT NULL,
  priority INTEGER NOT NULL,
  attempt INTEGER NOT NULL,
  max_attempts INTEGER NOT NULL,
  next_run_at TEXT,
  task_id TEXT,
  coalesced_into TEXT,
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  error_json TEXT NOT NULL DEFAULT '{}',
  operations_summary_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);

CREATE INDEX idx_manual_rebuild_jobs_kb_status
ON manual_rebuild_jobs(kb_name, status, created_at);
```

Do not store raw metadata JSON, document bodies, vectors, signed URLs, request headers, or stack traces.

## Configuration

Add under `manual_library`:

```yaml
rebuild_queue_enabled: false
rebuild_queue_durable: false
rebuild_queue_max_workers: 1
rebuild_queue_max_attempts: 2
rebuild_queue_retry_backoff_seconds: 5.0
rebuild_queue_history_limit: 100
```

Default behavior remains immediate rebuilds. Queueing is opt-in for M28 MVP.

## Coalescing Rules

When enqueueing a job for `kb_name`:

1. Find newest non-terminal job for that KB in `queued`, `retrying`, `running`, or `cancel_requested`.
2. If no such job exists, create a new queued job.
3. If a job exists:
   - `full` upgrades existing requested/effective mode to `full`.
   - `incremental` can merge into existing `incremental` or `auto`.
   - `auto` can merge into any existing queued job without weakening it.
   - `allow_fallback=false` makes the merged job strict unless existing job is already running; if already running and looser, create a follow-up queued strict job.
4. Return the existing/upgraded job with `coalesced=true`.

This avoids a rebuild storm after bulk uploads while still letting an operator force a full rebuild.

## Worker Model

MVP can run an in-process worker loop:

```text
enqueue job
  -> notify condition variable

worker loop
  -> acquire queue lock
  -> choose runnable jobs where:
       status in queued/retrying
       next_run_at <= now
       no running job for same KB
       global running count < max_workers
  -> mark job running
  -> start_library_rebuild()
  -> poll task.status until terminal or cancel requested
  -> mark succeeded/failed/retrying/cancelled
```

Implementation can start worker threads lazily when the first job is queued. Tests should be able to run workers synchronously or with deterministic fake executors.

## Cancellation Design

### Queued Jobs

Queued cancellation is straightforward:

```text
queued/retrying job + cancel
  -> status=cancelled
  -> finished_at=now
  -> dirty state unchanged
```

### Running Jobs

Running cancellation is cooperative:

```text
running job + cancel
  -> job.cancel_requested=true
  -> task.cancel_requested=true
  -> worker checks before major phases
  -> raises/returns cancelled before graph swap
```

Safe checkpoints:

- before registry/S3 staging starts
- after staging and before parsing/build
- before embedding batch starts, if practical
- before Qdrant sync
- before save/swap

Do not attempt hard thread interruption. If a running job passes the final swap point before cancellation is observed, it may complete as `succeeded`; the job payload should show `cancel_requested=true` for operator clarity.

## Retry Classification

Recommended helper:

```python
def retry_classification(error: dict | ServiceError | Exception) -> Literal["retryable", "terminal"]:
    ...
```

Retryable:

- `STORAGE_LOAD_FAILED` from S3/object-store get/head/put transient operations.
- `EMBEDDING_FAILED` when detail suggests HTTP status 429/500/502/503/504 or timeout.
- Qdrant sync connectivity or timeout failures.
- temporary staging cleanup/write errors where no graph swap occurred.

Terminal:

- `INVALID_CONFIG`.
- `INVALID_INPUT`.
- `STORAGE_SCHEMA_MISMATCH`.
- unsupported suffix/path traversal/metadata parse errors.
- missing optional dependency or missing credential env.
- cancellation.

Retries use bounded attempts and backoff:

```text
attempt 1 fails retryable
  -> status=retrying
  -> next_run_at = now + backoff * attempt
attempt >= max_attempts
  -> status=failed
```

## API Contracts

### Enqueue Rebuild

`POST /manual-library/rebuild`

When queueing disabled, keep the current task response.

When queueing enabled:

```json
{
  "job_id": "...",
  "status": "queued",
  "kb_name": "default",
  "requested_mode": "incremental",
  "effective_mode": "incremental",
  "allow_fallback": true,
  "coalesced": false,
  "task_id": null,
  "attempt": 0,
  "max_attempts": 2,
  "queue_position": 1,
  "operations_summary": null
}
```

### List Jobs

`GET /manual-library/rebuild-jobs?kb_name=default&status=queued&limit=50`

Returns:

```json
{"jobs": [{...}], "count": 1}
```

### Inspect Job

`GET /manual-library/rebuild-jobs/{job_id}`

Returns one job payload plus linked `rebuild_task` when available in current process.

### Cancel Job

`POST /manual-library/rebuild-jobs/{job_id}/cancel`

Returns updated job. Unknown job -> `INVALID_REQUEST`. Already terminal jobs return their current terminal status or an `INVALID_REQUEST`; choose one and test it.

### Retry Failed Job

Optional for MVP. `POST /manual-library/rebuild-jobs/{job_id}/retry` can create a new queued job from a failed job with the same safe request fields.

## CLI Contracts

Recommended commands:

```bash
python -m tagmemorag manual-library rebuild --kb default --mode auto --queued
python -m tagmemorag manual-library rebuild-jobs list --kb default --status queued
python -m tagmemorag manual-library rebuild-jobs inspect --job-id JOB_ID
python -m tagmemorag manual-library rebuild-jobs cancel --job-id JOB_ID
python -m tagmemorag manual-library rebuild-jobs retry --job-id JOB_ID
```

CLI output is JSON by default. `manual-library rebuild` may keep current synchronous behavior unless `--queued` is supplied or config enables queueing.

## Observability And Safety

Metrics labels should stay low-cardinality:

- `kb_name`
- `status`
- `operation`
- `outcome`

Potential metrics:

- `tagmemorag_rebuild_queue_depth`
- `tagmemorag_rebuild_queue_job_total`
- `tagmemorag_rebuild_queue_job_duration_seconds`
- `tagmemorag_rebuild_queue_retry_total`
- `tagmemorag_rebuild_queue_cancel_total`

Logs should include job id, KB name, status, attempt, task id, and safe error code. Do not log raw exception traces for known service errors, raw document text, vectors, credentials, or signed URLs.

## Rollout

1. Ship queue code disabled by default.
2. Enable queueing in local/dev with `max_workers=1`.
3. Validate upload storm coalescing and queued rebuild completion.
4. Enable retry for object-store/Qdrant transient failures.
5. Optionally enable durable queue when registry backend is SQLite.

## Rollback

- Set `manual_library.rebuild_queue_enabled=false` to return to immediate rebuild behavior.
- Queued dirty state remains pending and can be rebuilt with current immediate CLI/API commands.
- If durable queue rows are corrupt, mark non-terminal rows abandoned and rely on dirty-state inspection plus manual rebuild.

## Open Questions

- Should queued mode become the default after M28, or remain opt-in until M29 provides UI visibility?
  - Recommendation: opt-in for M28.
- Should durable queue require `registry_backend=sqlite`?
  - Recommendation: yes for MVP; file mode can use in-memory queue only.
- Should running cancellation block until task terminal status?
  - Recommendation: API cancel returns immediately with `cancel_requested`; job inspection reports terminal status later.
