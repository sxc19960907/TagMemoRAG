# implement.md - M7 Manual Library Admin UI

## Implementation Checklist

### Phase A - UI Infrastructure

- [x] Read M7 PRD/design and relevant backend/frontend-ish specs before coding.
- [x] Add any needed dependency such as `jinja2` to `pyproject.toml`.
- [x] Add `src/tagmemorag/web/` package structure.
- [x] Add template/static asset mounting in `api.py`.
- [x] Add `GET /admin/manual-library` route.
- [x] Add a route smoke test that the page returns HTML and expected shell elements.

### Phase B - API Client and Layout

- [x] Create `manual_library.html` shell with toolbar, table region, detail panel, upload dialog, and rebuild banner.
- [x] Create `manual_library.css` with responsive operations-console layout.
- [x] Create `manual_library.js` state container and fetch helpers.
- [x] Implement KB selector and token input behavior.
- [x] Implement `GET /manual-library` loading with loading/empty/error states.
- [x] Render manual table with all core M6 fields.

### Phase C - Filtering and Detail Panel

- [x] Add text/status/searchable/pending filters.
- [x] Add row selection and detail panel rendering.
- [x] Add metadata form population from selected record.
- [x] Add tag text conversion between array and comma/newline text.
- [x] Add validation action through `POST /manuals/validate`.
- [x] Add metadata save through `PATCH /manuals/{manual_id}/metadata`.

### Phase D - Upload and File Actions

- [x] Add upload dialog/form.
- [x] Validate upload metadata before submit.
- [x] Upload multipart through `POST /manuals`.
- [x] Implement overwrite and trigger rebuild toggles.
- [x] Implement source file replacement through `PUT /manuals/{manual_id}/file`.
- [x] Refresh library list after successful mutations.

### Phase E - Delete/Disable and Rebuild

- [x] Implement disable action with confirmation.
- [x] Implement hard delete with manual id confirmation.
- [x] Implement `POST /manual-library/rebuild`.
- [x] Poll `GET /rebuild/{task_id}` until done/failed.
- [x] Refresh list after rebuild finishes.
- [x] Show failed rebuild errors while leaving pending state visible.

### Phase F - Docs and Verification

- [x] Update README with `/admin/manual-library` route and local usage.
- [x] Add/adjust tests for static/template serving and any helper behavior.
- [x] Run focused tests for M6/M7 API/UI.
- [x] Run `uv run pytest tests/ -q`.
- [ ] Browser smoke test the page locally. HTTP-level local smoke passed; in-app browser automation timed out before rendering.
- [ ] Commit through Trellis finish flow.

## Validation

- `uv run pytest tests/unit/test_manual_library.py tests/unit/test_manual_library_api.py -q`
- `uv run pytest tests/unit/test_manual_library_ui.py -q`
- `uv run pytest tests/ -q`

Manual browser smoke:

1. Start the API server with hashing model/test config if needed.
2. Open `/admin/manual-library`.
3. Load `default` KB library.
4. Upload a Markdown manual with metadata.
5. Confirm it appears as unbuilt/pending.
6. Edit metadata and verify pending remains visible.
7. Trigger rebuild and watch task transition to done.
8. Confirm the record becomes searchable with chunk count.
9. Disable the manual, rebuild, and confirm it is no longer searchable.

## Review Gates

- [x] The UI does not duplicate server-side validation logic beyond client convenience formatting.
- [x] Existing JSON API clients are unaffected.
- [x] Auth errors are visible and tokens are not logged or embedded in HTML.
- [x] Destructive actions require confirmation.
- [x] The design remains usable on desktop and narrow screens.
- [x] Text does not overlap in table, toolbar, modal, or detail panel.
- [x] The page works without a Node build step.

## Rollback Points

- If template/static mounting becomes noisy, keep only the JSON APIs and defer UI.
- If vanilla JS grows too complex, pause before introducing a frontend build system and split a separate M8 SPA task.
- If auth UX becomes risky, support local unauthenticated deployments first and document token-paste auth as experimental.
