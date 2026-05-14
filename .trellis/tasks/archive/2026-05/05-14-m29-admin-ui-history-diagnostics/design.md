# design.md - M29 Admin UI History And Diagnostics

## Scope

M29 extends the existing manual-library admin surface. It should not rewrite manual upload/update/delete, registry storage, blob store implementations, rebuild execution, WAVE search, Qdrant sync, or retrieval ranking.

Primary work:

- Add safe diagnostics API payloads.
- Add registry/audit/blob/queue panels to the existing admin page.
- Update JavaScript polling/control flow for queue-enabled rebuilds.
- Update CSS and tests to preserve a dense operational UI.

## Current State

```text
GET /admin/manual-library
  -> Jinja shell
  -> manual_library.js
     -> GET /manual-library
     -> POST /manuals
     -> POST /manual-library/bulk/*
     -> POST /manual-library/rebuild
        -> currently assumes task_id and polls GET /rebuild/{task_id}
```

Available backend data:

- `GET /manual-library`: manual list, pending dirty state, dirty manual rows.
- `GET /manual-library/dirty`: dirty report, operations summary, recovery actions, last impact/Qdrant hints.
- `registry_inspect()`: registry backend, record count, status counts, blob backend.
- `verify_registry_blobs()`: checked/missing blob counts and missing rows.
- `SQLiteManualRegistry.audit_events()`: audit events for KB/manual.
- M28 queue endpoints:
  - `GET /manual-library/rebuild-jobs`
  - `GET /manual-library/rebuild-jobs/{job_id}`
  - `POST /manual-library/rebuild-jobs/{job_id}/cancel`
  - `POST /manual-library/rebuild-jobs/{job_id}/retry`

## Target Data Flow

```text
Admin page load / KB switch
  -> loadManuals()
  -> loadDiagnostics()
       -> GET /manual-library/diagnostics?kb_name=...
       -> render summary bands, recovery actions, queue jobs, registry/blob status
  -> loadAuditTimeline()
       -> GET /manual-library/registry/audit?kb_name=...&limit=...

Manual selection
  -> render manual detail
  -> loadAuditTimeline(manual_id)

Rebuild button
  -> POST /manual-library/rebuild
     if response.task_id:
       poll GET /rebuild/{task_id}
     if response.job_id:
       poll GET /manual-library/rebuild-jobs/{job_id}
       refresh job list and diagnostics

Queue action
  -> POST /manual-library/rebuild-jobs/{job_id}/cancel|retry
  -> refresh diagnostics/job list
```

## Proposed API Additions

### `GET /manual-library/diagnostics`

Parameters:

- `kb_name: str = "default"`
- `verify_blobs: bool = false`
- `include_jobs: bool = true`
- `job_status: str | None = None`

Auth:

- `require_scope("rebuild")`
- `ensure_kb_access(api_key, kb_name)`

Response:

```json
{
  "kb_name": "default",
  "registry": {
    "enabled": true,
    "registry_backend": "sqlite",
    "record_count": 12,
    "status_counts": {"active": 10, "disabled": 1, "deleted": 1},
    "blob_backend": "s3"
  },
  "blob_health": {
    "checked": true,
    "checked_count": 12,
    "missing_count": 1,
    "missing": [{"manual_id": "cm1", "blob_key": "default/cm1/1.md", "blob_backend": "s3"}]
  },
  "dirty": {
    "pending_changes": true,
    "dirty_manual_count": 2,
    "recovery_actions": ["inspect_dirty", "retry_incremental", "force_full_rebuild"],
    "operations_summary": {}
  },
  "rebuild_queue": {
    "enabled": true,
    "jobs": []
  },
  "recommendations": [
    {"code": "verify_blobs", "label": "Verify registry blobs", "severity": "warning"},
    {"code": "retry_rebuild", "label": "Retry queued rebuild", "severity": "warning"}
  ]
}
```

Rules:

- If registry is disabled, `registry.enabled=false` and `blob_health.checked=false`.
- `verify_blobs=false` should not perform remote S3 `head` calls. It may return the latest known or unchecked state.
- If queue is disabled, `rebuild_queue.enabled=false` and jobs is empty.
- `recommendations` are derived only from safe statuses and counts.

### `GET /manual-library/registry/audit`

Parameters:

- `kb_name: str = "default"`
- `manual_id: str | None = None`
- `limit: int = 50`

Auth:

- `require_scope("rebuild")`
- `ensure_kb_access(api_key, kb_name)`

Response:

```json
{
  "kb_name": "default",
  "enabled": true,
  "events": [
    {
      "event_id": "...",
      "manual_id": "cm1",
      "operation": "file_replace",
      "outcome": "success",
      "version": 3,
      "actor_id": "",
      "created_at": "2026-05-14T...",
      "detail": {
        "source_file": "coffee/cm1.md",
        "status": "active",
        "size_bytes": 1234,
        "blob_backend": "s3"
      }
    }
  ]
}
```

Rules:

- Sort newest first.
- Clamp `limit` to a safe maximum, for example 200.
- If registry is disabled, return `enabled=false` and `events=[]`.
- Detail must be sanitized. Do not include metadata text samples, raw JSON dumps with arbitrary user notes if they become unsafe, source bytes, signed URLs, credentials, headers, or stack traces.

### Blob Verification Endpoint

Two acceptable implementation choices:

1. Include `verify_blobs=true` on diagnostics and call `verify_registry_blobs()`.
2. Add `POST /manual-library/registry/verify-blobs` returning the same safe shape.

Recommendation: implement `verify_blobs=true` first to keep the route surface small, then add a dedicated endpoint only if the UI needs explicit long-running verification state.

## UI Layout

Keep the current topbar and library/detail layout. Add an operations band below the status strip and above filters:

```text
Topbar
Status strip
Operations band
  Registry | Blob Health | Dirty State | Rebuild Queue | Last Rebuild/Qdrant
Filters
Workspace
  Library table
  Detail pane
    Existing metadata edit sections
    New tabs/sections:
      Diagnostics
      Audit Timeline
Dialogs
  Existing upload/bulk/tag dialogs
```

Recommended controls:

- Use small status pills for `active`, `missing`, `queued`, `running`, `failed`, `retrying`.
- Use table rows for queue jobs and audit events.
- Use buttons for clear commands: Verify blobs, Cancel job, Retry job, Force full rebuild.
- Use collapsible details only for secondary safe JSON detail.
- Avoid nested cards. Panels should be sibling sections or table bands.

## JavaScript State Shape

Add fields to `state` in `manual_library.js`:

```js
{
  diagnostics: null,
  rebuildJobs: [],
  selectedJobId: null,
  auditEvents: [],
  auditManualId: null,
  diagnosticsRefreshing: false
}
```

New functions:

- `loadDiagnostics({ verifyBlobs = false } = {})`
- `renderDiagnostics()`
- `renderRebuildJobs()`
- `pollRebuildJob(jobId)`
- `cancelRebuildJob(jobId)`
- `retryRebuildJob(jobId)`
- `loadAuditTimeline(manualId = null)`
- `renderAuditTimeline()`
- `recommendationLabel(code)`

Existing `pollRebuild(taskId)` should stay for immediate mode.

Rebuild trigger handling:

```js
const response = await apiFetch("/manual-library/rebuild", ...)
if (response.job_id) pollRebuildJob(response.job_id)
else if (response.task_id) pollRebuild(response.task_id)
```

Upload/bulk trigger handling should show either:

- "Manual uploaded and rebuild job queued."
- "Manual uploaded and rebuild started."
- "Manual uploaded. Rebuild is required before it is searchable."

## Backend Implementation Notes

- Put diagnostics assembly in `manual_library.py` if it is reusable by CLI/API, or keep it in `api.py` if it is purely response orchestration. Prefer `manual_library.py` if recommendations become testable domain logic.
- Reuse existing helpers:
  - `registry_inspect`
  - `verify_registry_blobs`
  - `build_dirty_state_report`
  - `RebuildQueue.list_jobs`
  - `SQLiteManualRegistry.audit_events`
- Add a small `audit_timeline()` helper if route logic would otherwise open registry internals directly.
- Keep ServiceError shape consistent.
- If any registry audit detail contains unsafe or unexpectedly large values, sanitize and cap it before response.

## Safety And Privacy

Allowed fields:

- manual id
- source file
- status
- version
- operation
- outcome
- timestamps
- checksum if already exposed elsewhere and useful
- blob backend
- safe blob key
- counts and statuses
- stable error code/type/message from M28 safe job payloads

Forbidden fields:

- raw document body
- chunk text
- embedding vectors
- credentials or environment values
- signed URLs
- request headers
- raw stack traces
- full local absolute paths unless already part of an existing safe admin response
- high-cardinality debug dumps

## Error Handling

- Registry disabled: return successful payload with `enabled=false`.
- Queue disabled: return successful payload with `rebuild_queue.enabled=false`.
- Blob verification failure: return structured `ServiceError` if the operator explicitly requested verification; otherwise diagnostics should still load with `blob_health.error`.
- Audit unavailable due to missing/corrupt registry DB: return structured storage/config error and keep the UI status strip actionable.
- Auth failure uses existing auth dependencies.

## Testing Strategy

Backend:

- diagnostics with file-sidecar mode
- diagnostics with sqlite registry enabled
- diagnostics with `verify_blobs=true` and fake missing blob
- audit endpoint returns newest-first events and filters by manual
- queue disabled diagnostics
- queue enabled diagnostics with fake queued/failed job
- auth/scope and KB allowlist checks

Frontend/static shell:

- admin route includes new diagnostics containers
- JS contains expected endpoint calls and queue polling branch
- CSS contains stable layout classes and responsive rules

Integration-ish unit:

- upload with `trigger_rebuild=true` and queue enabled returns `rebuild_job`, UI code path should be represented in JS tests or static assertions.

## Rollout

1. Ship backend diagnostics endpoints with no UI dependency.
2. Add UI read-only panels for registry, dirty, blob, audit, and queue.
3. Add queue actions: cancel and retry.
4. Add explicit blob verification action.
5. Update README and tests.

## Rollback

- UI additions are static assets and template sections; rollback by reverting M29 files.
- If diagnostics endpoint causes operational issues, hide UI calls behind graceful failure while keeping existing manual list working.
- Queue actions can be hidden independently of read-only job list if needed.

## Open Questions

- Should blob verification run automatically on page load for local blob backend only, while S3 requires explicit click?
  - Recommendation: local can auto-run; S3 should require explicit verify.
- Should audit timeline include deleted manual records by default?
  - Recommendation: yes for registry audit events, but clearly mark deleted status.
- Should diagnostics become a standalone route separate from manual-library admin?
  - Recommendation: keep M29 inside the existing manual-library page; split later only if the page becomes too dense.
