# M29 Admin UI History And Diagnostics

## Goal

Extend the existing manual-library admin UI into an operational console for managed manual history and rebuild diagnostics. M29 should surface registry records, blob health, audit timeline, dirty-state recovery, rebuild queue status, and safe failure details in one dense, scan-friendly workflow.

The UI should help an operator answer:

- What changed in this KB and which manuals are affected?
- Are registry records and blob references healthy?
- Is a rebuild queued, running, retrying, cancelled, or failed?
- Which recovery action should be taken next?
- Did the latest rebuild clear dirty state and update Qdrant/blob/impact summaries?

## Background / Known Context

- M6 introduced the manual-library admin page at `GET /admin/manual-library`.
- M10/M11/M12 expanded the page with bulk import, tag governance, suggestions, and retrieval quality links.
- M21 added dirty-state reports, rebuild operation summaries, and recovery hints.
- M26 added SQLite registry records, blob references, and audit events.
- M27 added S3-compatible blob storage behind the blob-store boundary.
- M28 added an opt-in in-process rebuild queue with job list/inspect/cancel/retry API endpoints.
- The current admin UI already lists manuals and can trigger immediate rebuilds, but it does not expose queue jobs, audit history, blob verification results, migration/registry state, or focused recovery diagnostics.

## Problem

Operators currently need to switch between CLI commands, raw JSON endpoints, logs, and the admin UI to understand managed-library state. That makes failure recovery slower and easier to get wrong:

- A failed S3-backed rebuild can leave dirty state pending, but the page does not show blob verification or the failing job detail.
- Queue-enabled deployments return rebuild jobs instead of task IDs, but the current UI only polls `GET /rebuild/{task_id}`.
- Registry/audit state exists in SQLite but has no UI path.
- Dirty-state recovery hints are available as JSON but not grouped with rebuild queue and manual history.
- Bulk import or repeated uploads can coalesce into a queued rebuild, but operators cannot see the coalesced job from the UI.

## Requirements

### 1. Operational Overview

- Add a diagnostics area to the existing manual-library admin page.
- Show concise status cards or compact summary rows for:
  - registry backend and enabled state
  - blob backend and latest verification status
  - pending dirty state and dirty manual count
  - latest rebuild queue status when queueing is enabled
  - latest rebuild task/impact summary when available
  - Qdrant sync summary when available
- Summaries must use safe, low-cardinality fields only.
- The UI must remain dense and operational, not a marketing page or dashboard hero.

### 2. Registry Records And Blob Health

- Surface registry inspection data when `manual_library.registry_backend=sqlite`:
  - total record count
  - status counts
  - blob backend
  - registry path may be shown only if already exposed by existing inspect output; avoid expanding path detail elsewhere.
- Add a blob health panel backed by `verify_registry_blobs()`:
  - checked count
  - missing count
  - missing manual ids and safe blob keys
- If registry mode is disabled, show file-sidecar mode clearly without treating it as an error.
- Blob verification should be triggered explicitly or refreshed on page load only if cheap enough; avoid long blocking work on every routine list refresh if S3 latency is high.

### 3. Audit Timeline

- Add API/UI access to registry audit events:
  - filter by `kb_name`
  - optional filter by `manual_id`
  - limit result count
  - show operation, outcome, version, actor id when present, created_at, and safe detail fields
- Do not show raw document text, source bytes, vectors, credentials, signed URLs, request headers, or stack traces.
- Timeline order should default to newest first in API/UI even if the low-level registry returns chronological rows.
- File-sidecar mode should return an empty timeline with `enabled=false` or a clear message rather than a hard failure.

### 4. Rebuild Queue Visibility

- When `manual_library.rebuild_queue_enabled=true`, the UI must:
  - call `GET /manual-library/rebuild-jobs?kb_name=...`
  - render job status, requested/effective mode, attempt count, max attempts, task id, queue position, error summary, and updated time
  - support inspect details for a selected job
  - support cancel for queued/running/retrying jobs
  - support retry for failed jobs
  - handle coalesced job responses from upload/bulk/rebuild triggers
- When queueing is disabled, the UI must preserve existing immediate rebuild behavior and task polling.
- Queue job details must be safe and should not expose raw stack traces or high-cardinality payload dumps.

### 5. Recovery Guidance

- Group recovery actions from dirty-state reports, queue failures, blob verification, registry mode, and Qdrant sync summaries into a single operator-focused section.
- Recommended actions should be explicit and scriptable, for example:
  - inspect dirty state
  - retry queued rebuild
  - cancel superseded queued job
  - force full rebuild
  - verify registry blobs
  - restore object store availability
  - temporarily roll back to file/NPZ mode when appropriate
- The UI should not auto-run destructive actions such as hard delete, registry migration, or config rollback.

### 6. API Contracts

- Add safe admin-support endpoints if current endpoints are insufficient, likely:
  - `GET /manual-library/diagnostics?kb_name=...`
  - `GET /manual-library/registry/audit?kb_name=...&manual_id=...&limit=...`
  - `POST /manual-library/registry/verify-blobs` or equivalent JSON endpoint if the current CLI-only path is not exposed
- Endpoints must require `rebuild` scope, plus KB allowlist access. Destructive or future migration actions should require `admin`.
- Existing endpoint semantics must remain backward compatible.

### 7. UI Compatibility

- Keep one server-rendered shell and vanilla JS/static CSS unless a future milestone explicitly changes the frontend stack.
- Preserve existing manual list, detail editor, upload, bulk import, tag governance, and rebuild controls.
- The page must fit common desktop operator workflows and remain usable on narrow screens.
- Do not put cards inside cards; use full-width panels, tables, tabs, or compact bands.
- Text must not overlap or overflow controls.

### 8. Documentation

- README should document:
  - where to find diagnostics UI
  - what each operational panel means
  - queue-enabled vs immediate rebuild behavior
  - safe recovery flows for dirty state, missing blobs, failed queue jobs, and Qdrant sync uncertainty

## Acceptance Criteria

- [ ] PRD/design/implementation plan exist before implementation starts.
- [ ] Existing manual-library admin workflows continue to work.
- [ ] Admin UI shows registry summary and file-sidecar fallback state.
- [ ] Admin UI can show blob verification status and missing blob rows without leaking secrets.
- [ ] Admin UI can show audit timeline entries for a KB and selected manual.
- [ ] Admin UI can show rebuild queue jobs, inspect job detail, cancel active jobs, and retry failed jobs when queueing is enabled.
- [ ] Immediate rebuild mode remains supported when queueing is disabled.
- [ ] Diagnostics panel groups dirty-state, rebuild, blob, registry, and Qdrant recovery signals.
- [ ] API endpoints enforce existing auth scope and KB allowlist patterns.
- [ ] Focused API/UI tests cover registry-disabled, registry-enabled, queue-disabled, queue-enabled, missing blob, and audit timeline states.
- [ ] `uv run pytest tests/ -q` passes.

## Definition Of Done

- M29 documentation is complete and checked into `.trellis/tasks/`.
- Implementation follows existing FastAPI, vanilla JS, Jinja template, and CSS patterns.
- All new payloads are safe by design.
- No external services are required for default tests; S3/Qdrant/blob failures use fakes.
- README includes operator guidance and rollback/recovery notes.

## Out Of Scope For M29 MVP

- Durable rebuild queue persistence.
- Multi-replica queue coordination or leader election.
- Registry migration repair/write actions beyond existing migrate/verify support.
- Import/export bundles; M30 owns portable bundles.
- Production deployment runbooks; M31 owns deployment docs.
- Replacing the current server-rendered/vanilla JS admin UI with a SPA framework.
- Visualization-heavy dashboards or charting libraries.

## Research References

- `.trellis/workspace/suixingchen/roadmap.md`
- `.trellis/tasks/archive/2026-05/05-14-m26-manual-registry-blob-storage/`
- `.trellis/tasks/archive/2026-05/05-14-m27-s3-compatible-blob-store/`
- `.trellis/tasks/archive/2026-05/05-14-m28-background-rebuild-queue-cancellation/`
- `src/tagmemorag/api.py`
- `src/tagmemorag/manual_library.py`
- `src/tagmemorag/manual_registry.py`
- `src/tagmemorag/rebuild_queue.py`
- `src/tagmemorag/web/templates/manual_library.html`
- `src/tagmemorag/web/static/manual_library.js`
- `src/tagmemorag/web/static/manual_library.css`
- `tests/unit/test_manual_library_ui.py`
- `tests/unit/test_manual_library_api.py`
