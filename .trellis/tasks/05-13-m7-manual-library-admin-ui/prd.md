# M7 Manual Library Admin UI

## Goal

Build a lightweight browser UI for the M6 managed manual library so an operator can upload manuals, validate/edit metadata, disable/delete manuals, and trigger library rebuilds without hand-writing curl commands. The UI should make pending rebuild state obvious while preserving the current API-first backend and WAVE-RAG serving behavior.

## Background / Known Context

- M6 added the managed manual library API:
  - `POST /manuals/validate`
  - `POST /manuals`
  - `PATCH /manuals/{manual_id}/metadata`
  - `PUT /manuals/{manual_id}/file`
  - `DELETE /manuals/{manual_id}`
  - `GET /manual-library`
  - `POST /manual-library/rebuild`
- Existing `GET /manuals` remains graph-derived for search-facing clients.
- Manual library changes are not searchable until a successful `POST /manual-library/rebuild`.
- Auth already protects JSON API operations through existing scopes and KB allowlists.
- The repository currently has no frontend build pipeline. The runtime is FastAPI/Python.

## Product Direction

M7 should be an operations/admin tool, not a marketing page or full product dashboard. It should feel quiet, information-dense, and reliable:

- Fast to scan.
- Clear about pending/searchable/rebuild states.
- Conservative around destructive actions.
- Usable with the existing FastAPI server.

## Recommended Stack

Use server-rendered FastAPI UI with:

- Jinja2 templates for initial HTML.
- Static CSS for layout and visual design.
- Small vanilla JavaScript for file upload, metadata validation, table filtering, and rebuild polling.
- Optional HTMX-style progressive enhancement only if it materially reduces JS complexity.

Do not add React/Vue/Vite in M7 unless implementation discovers a hard blocker. A SPA build system would add deployment complexity that is not justified by this admin UI.

## Requirements

### 1. Admin UI Route

- Add a browser page, recommended route: `GET /admin/manual-library`.
- The page should be served by the same FastAPI app.
- The route should not replace existing JSON APIs.
- The page must work in the default local dev flow after `python -m tagmemorag serve`.

### 2. KB Selection and Library Overview

- Show a KB selector.
- Default to `default` when no KB is provided.
- Load managed manuals from `GET /manual-library?kb_name=...`.
- Show empty, loading, and error states.
- Show the library root when returned by the API.

### 3. Manual Table

Show a scan-friendly table with at least:

- `status`
- `manual_id`
- title
- source file
- product category
- product model
- language
- tags
- `searchable`
- `chunk_count`
- `rebuild_required`
- updated timestamp

Filtering should include:

- text search across manual id/title/source/model/category
- lifecycle status
- searchable/unbuilt
- rebuild required

### 4. Detail and Metadata Editing

- Selecting a row opens a detail/edit panel.
- Display the current normalized metadata.
- Allow editing common metadata fields:
  - title
  - source file
  - brand
  - product category
  - product name
  - product model
  - language
  - version
  - tags
  - notes
  - status
- Provide a raw JSON view or advanced section for fields not covered by primary controls.
- Validate metadata before saving by calling `POST /manuals/validate`.
- Save metadata through `PATCH /manuals/{manual_id}/metadata`.
- After save, refresh the list and keep pending rebuild state visible.

### 5. Upload Manual

- Provide an upload modal or panel.
- Accept `.md`, `.txt`, and text-based `.pdf`.
- Capture metadata alongside the file.
- Validate metadata before upload.
- Support explicit overwrite toggle.
- Support optional trigger rebuild toggle, default off.
- Upload through `POST /manuals` multipart.
- Show actionable validation messages from the API.

### 6. Replace Source File

- From the detail panel, allow replacing the source file for an existing manual.
- Use `PUT /manuals/{manual_id}/file`.
- Warn that large content changes may leave anchors unresolved until after rebuild reconciliation.

### 7. Disable and Hard Delete

- Soft disable should be easy but confirmed.
- Hard delete should be visually separated, require a stronger confirmation, and call `DELETE /manuals/{manual_id}?hard=true`.
- The UI should explain that disabled manuals remain on disk and are excluded from future rebuilds.

### 8. Rebuild Flow

- Provide a primary `Rebuild library` action.
- Call `POST /manual-library/rebuild`.
- Poll `GET /rebuild/{task_id}` until done/failed.
- Show running, success, and failure states.
- On success, refresh `GET /manual-library`.
- On failure, keep pending state visible and show the error payload.

### 9. Authentication UX

- M7 does not need full login/session management.
- For local/admin usage, the page can rely on the same deployment auth policy as the API.
- If auth is enabled and browser calls need a token, provide a token input stored only in memory or `sessionStorage`; do not persist tokens in files.
- API errors `401/403/429` should be shown clearly.

### 10. Documentation

- Update README with the UI route and local usage notes.
- Document the supported stack and the fact that JSON APIs remain canonical.

## Acceptance Criteria

- [ ] Visiting `/admin/manual-library` renders a usable admin page.
- [ ] The UI can list managed manuals for a KB through the M6 API.
- [ ] The table supports text/status/searchable/pending filters.
- [ ] The UI can validate metadata and show normalized tags/messages.
- [ ] The UI can upload a manual with metadata and show it in the library list before rebuild.
- [ ] The UI can edit metadata and mark/display pending rebuild state.
- [ ] The UI can replace a source file.
- [ ] The UI can disable a manual and hard delete with confirmation.
- [ ] The UI can trigger a library rebuild, poll task status, and refresh after success.
- [ ] Existing JSON API tests and M6 behavior remain compatible.
- [ ] Tests cover UI route availability, static/template serving, and key browser/API interactions at an appropriate level.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- UI is implemented and visually checked in a browser.
- `uv run pytest tests/ -q` passes.
- Any added dependencies are documented in `pyproject.toml`.
- README explains how to open and use the admin UI.

## Out of Scope

- Full login/session management.
- Multi-user collaboration, audit history UI, or DB-backed registry.
- OCR pipeline UI.
- Product-grade SPA build pipeline.
- Advanced role management beyond existing API scopes.
- WYSIWYG manual editing.
- Cross-KB federated dashboards.

## Follow-Up Ideas

- Dedicated auth/session UI.
- Audit timeline once registry storage exists.
- OCR extraction status panel.
- Bulk import and bulk metadata editing.
- Tag suggestion UX.
