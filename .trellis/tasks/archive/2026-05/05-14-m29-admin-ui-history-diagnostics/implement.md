# implement.md - M29 Admin UI History And Diagnostics

## Implementation Checklist

- [ ] Read backend specs with `trellis-before-dev` before coding.
- [ ] Re-read M26, M27, and M28 archived task docs.
- [ ] Inspect current admin UI template, CSS, and JS before editing.
- [ ] Add diagnostics API contracts:
  - `GET /manual-library/diagnostics`
  - `GET /manual-library/registry/audit`
  - optional explicit blob verification endpoint if not using `verify_blobs=true`
- [ ] Add safe backend helper(s) for diagnostics and recommendations.
- [ ] Add audit timeline helper using `SQLiteManualRegistry.audit_events()`.
- [ ] Add UI containers for operations/diagnostics band.
- [ ] Add UI rendering for registry summary, blob health, dirty state, recommendations, queue jobs, and audit timeline.
- [ ] Update rebuild trigger flow to branch on `job_id` vs `task_id`.
- [ ] Add queue job inspect/cancel/retry UI behavior.
- [ ] Add explicit blob verification action.
- [ ] Preserve existing upload, bulk import, tag governance, detail edit, disable/delete, and immediate rebuild behavior.
- [ ] Update README operator docs.
- [ ] Add focused backend/API tests.
- [ ] Add admin shell/static asset tests.
- [ ] Run focused tests and full suite.

## Suggested Implementation Phases

### Phase A - Backend Diagnostics Contracts

- Add helper to assemble diagnostics from existing data:
  - `registry_inspect`
  - `build_dirty_state_report`
  - `verify_registry_blobs` when requested
  - current `rebuild_queue` if enabled
- Add recommendations derived from counts/statuses.
- Add audit endpoint with limit clamp and newest-first ordering.
- Keep registry-disabled and queue-disabled as successful states.

Validation:

```bash
uv run pytest tests/unit/test_manual_library_api.py -q
```

### Phase B - UI Read-Only Diagnostics

- Add operations band and timeline containers to `manual_library.html`.
- Add JS state and `loadDiagnostics()` / `renderDiagnostics()`.
- Add audit timeline load/render and manual-selection filtering.
- Add CSS for dense tables/status pills/responsive layout.

Validation:

```bash
uv run pytest tests/unit/test_manual_library_ui.py -q
```

### Phase C - Queue-Aware Rebuild Controls

- Update rebuild button handler:
  - `task_id` -> existing `pollRebuild`
  - `job_id` -> new `pollRebuildJob`
- Update upload/bulk import status messages for `rebuild_job`.
- Render queue job list.
- Add cancel/retry buttons and refresh after actions.

Validation:

```bash
uv run pytest tests/unit/test_manual_library_api.py tests/unit/test_manual_library_ui.py tests/unit/test_rebuild_queue.py -q
```

### Phase D - Blob Verification And Recovery Actions

- Add Verify blobs action.
- Add recommendation chips/rows that point to existing safe actions.
- Ensure S3 verification errors show as actionable UI errors without breaking manual list refresh.

Validation:

```bash
uv run pytest tests/unit/test_manual_blob_store.py tests/unit/test_manual_library_api.py -q
```

### Phase E - Docs And Full Validation

- Update README with diagnostics UI and recovery flows.
- Check CSS color/layout does not regress into a one-note theme.
- Run full test suite.

Validation:

```bash
uv run pytest tests/ -q
```

## Focused Tests To Add

- Diagnostics endpoint returns file-sidecar fallback with `registry.enabled=false`.
- Diagnostics endpoint returns sqlite registry counts and blob backend.
- Diagnostics endpoint with `verify_blobs=true` reports missing fake blob safely.
- Diagnostics endpoint returns queue disabled state by default.
- Diagnostics endpoint returns queue jobs when queueing is enabled.
- Audit endpoint returns `enabled=false` in file-sidecar mode.
- Audit endpoint returns newest-first events and supports `manual_id` filter.
- Audit endpoint clamps `limit`.
- Auth-enabled diagnostics requires `rebuild` scope and KB access.
- Admin shell includes diagnostics band, queue job table, blob verify button, and audit timeline containers.
- Static JS references diagnostics/audit/queue endpoints.
- Queue-enabled rebuild response with `job_id` does not call task polling path in new code.

## Review Gates

- Existing admin workflows still work.
- Existing immediate rebuild path still works when queue disabled.
- Queue UI does not assume durable jobs survive restart.
- Registry disabled is a normal state, not an error.
- Blob verification is explicit or cheap; S3-heavy checks are not run on every refresh by accident.
- Payloads do not leak raw text, vectors, credentials, signed URLs, headers, or stack traces.
- UI remains dense, scannable, and responsive.

## Validation

Focused:

```bash
uv run pytest tests/unit/test_manual_library_api.py -q
uv run pytest tests/unit/test_manual_library_ui.py -q
uv run pytest tests/unit/test_rebuild_queue.py -q
```

Full:

```bash
uv run pytest tests/ -q
```

## Rollback Points

- If diagnostics endpoint scope grows too much, ship read-only dirty/queue/registry summaries first and defer audit/blob verify.
- If queue action UI is risky, ship job list/inspect first and keep cancel/retry API-only for one milestone.
- If the existing page gets too dense, add tabs inside the right detail pane rather than creating a new frontend stack.
