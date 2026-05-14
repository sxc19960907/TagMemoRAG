# Code Context - M29 Admin UI History And Diagnostics

## Existing UI Entry Points

- `src/tagmemorag/api.py`
  - `GET /admin/manual-library` renders the Jinja shell.
  - Manual-library API routes already support list/upload/update/delete/bulk/tag/rebuild.
  - M28 queue endpoints exist for list/inspect/cancel/retry.

- `src/tagmemorag/web/templates/manual_library.html`
  - Current single-page admin shell.
  - Topbar has KB selector, API token, bulk/tags/upload buttons, rebuild mode, rebuild button.
  - Main body has status strip, filters, manual table, detail pane, upload dialog, bulk dialog, tag governance dialog.

- `src/tagmemorag/web/static/manual_library.js`
  - Owns all vanilla JS state/rendering.
  - `loadManuals()` calls `GET /manual-library`.
  - `pollRebuild(taskId)` assumes low-level rebuild task ids.
  - Upload/bulk/rebuild handlers need queue-aware `job_id` handling for M29.

- `src/tagmemorag/web/static/manual_library.css`
  - Existing dense operational styling.
  - Uses light neutral palette, compact tables, sticky topbar, dialogs, and responsive layout.

## Existing Diagnostics Sources

- `build_dirty_state_report(kb_name, cfg, graph_state=...)`
  - Returns pending state, dirty manual rows, current/last build ids, recovery actions, operations summary, and rebuild impact hints.

- `registry_inspect(kb_name, cfg)`
  - Returns registry enabled/backend/path, record count, status counts, and blob backend.
  - Returns `enabled=false` when registry backend is file-sidecar.

- `verify_registry_blobs(kb_name, cfg)`
  - Requires sqlite registry mode.
  - Returns checked/missing counts and safe missing rows.

- `SQLiteManualRegistry.audit_events(kb_name, manual_id=None)`
  - Returns operation/outcome/version/actor/created_at/detail.
  - Current low-level order is chronological; M29 API should return newest first.

- `RebuildQueue`
  - In-process queue only.
  - Safe job payload includes job id, KB, mode, status, task id, attempts, next run, cancel flag, error summary, operations summary, queue position.

## Relevant Tests

- `tests/unit/test_manual_library_ui.py`
  - Asserts admin route and static assets contain expected IDs/endpoints.

- `tests/unit/test_manual_library_api.py`
  - Covers manual upload/list/dirty/rebuild, tag governance, and queued rebuild API smoke.

- `tests/unit/test_rebuild_queue.py`
  - Covers coalescing, cancellation, retry classifier, and queue execution.

- `tests/unit/test_manual_blob_store.py`
  - Has fake blob/S3 patterns useful for missing blob tests.

- `tests/unit/test_cli.py`
  - Has registry inspect/migrate/verify CLI coverage.

## Suggested Implementation Shape

- Add small backend helpers rather than assembling complex diagnostics in JS.
- Keep frontend state additions local to `manual_library.js`.
- Use table rendering for queue jobs/audit events; avoid large raw JSON blocks except collapsed safe details.
- Make diagnostics refresh tolerant: if diagnostics fails, keep manual list usable and show error in status strip.
- Treat queue-disabled and registry-disabled as normal deployment modes.

## Main Risks

- Accidentally running S3 blob verification too often and making page refresh slow.
- Leaking unsafe audit detail or blob configuration.
- Breaking immediate rebuild polling by assuming all rebuilds return job ids.
- Making the page too visually busy. Use compact panels, tabs/sections, and status chips.
- Cross-layer drift between diagnostics API shape and JS render expectations.
