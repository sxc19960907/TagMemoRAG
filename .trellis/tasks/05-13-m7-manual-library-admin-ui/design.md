# design.md - M7 Manual Library Admin UI

## Scope

M7 adds a browser-admin layer on top of the M6 manual library API. It should not move business logic into the frontend. The M6 JSON endpoints remain the source of truth for validation, mutations, rebuild state, auth, and error handling.

## Target Experience

```text
GET /admin/manual-library
  -> server-rendered shell
  -> static CSS/JS
  -> fetch M6 JSON APIs
  -> update table/detail/upload/rebuild states in browser
```

The page is an admin work surface:

- Compact top toolbar with KB selector, token input when needed, upload, and rebuild.
- Main table for managed manuals.
- Right-side detail panel for metadata and file actions.
- Modal/dialog for upload.
- Inline banners for validation/rebuild/auth errors.

## Technology Decision

### Chosen

- FastAPI route for the page.
- Jinja2 template for the initial HTML document.
- `StaticFiles` for CSS/JS assets.
- Vanilla JavaScript modules/classes for state and API calls.

### Why

- The project already runs FastAPI and has no Node build step.
- The UI is CRUD-heavy and operational, not a complex client application.
- Deployment remains one Python service.
- Tests can use existing FastAPI `TestClient`; browser smoke can be manual or added later with a browser tool.

### Deferred

- React/Vue/Vite can be introduced later if the UI becomes a product surface with complex routing, component reuse, and design-system needs.

## Proposed Files

```text
src/tagmemorag/web/
  __init__.py
  templates/
    manual_library.html
  static/
    manual_library.css
    manual_library.js
```

Potential tests:

```text
tests/unit/test_manual_library_ui.py
```

## Routing

Add to `api.py`:

- Mount static directory, for example `/static/manual-library/...`.
- `GET /admin/manual-library` returns the template.

The UI shell should receive lightweight server-side config only:

- default KB name
- API base path, likely empty string
- auth enabled flag
- app title/version if useful

Do not inject API secrets into the template.

## Frontend State Model

Browser state:

```js
{
  kbName: "default",
  apiToken: "",
  manuals: [],
  selectedManualId: null,
  filters: {
    text: "",
    status: "all",
    searchable: "all",
    pending: "all"
  },
  rebuildTask: null,
  loading: false,
  error: null
}
```

All canonical data is reloaded from `GET /manual-library` after mutations.

## API Client Behavior

Use `fetch()` wrappers:

- Add `Authorization: Bearer ${token}` only when token is present.
- Parse structured service errors `{code, message, detail}`.
- Convert validation messages into field-level or form-level UI messages.
- Do not log tokens, file content, or raw manual text.

## Upload Form

Fields:

- file input
- `manual_id`
- title
- source file
- product category
- brand
- product name
- product model
- language
- version
- tags as comma/newline-separated text
- notes
- overwrite toggle
- trigger rebuild toggle

Metadata conversion:

- split tags on comma/newline
- trim empty values
- send as JSON string in multipart `metadata`

Validation flow:

```text
Edit fields -> Validate button -> POST /manuals/validate
  valid -> show normalized metadata and enable upload/save
  invalid -> show messages, keep form editable
```

## Detail Panel

Primary actions:

- validate metadata
- save metadata
- replace file
- disable manual
- hard delete

Destructive actions should use browser confirmation or an in-page confirmation control:

- Disable: confirm by clicking a secondary confirmation button.
- Hard delete: require typing the manual id before enabling the final button.

## Rebuild Polling

Flow:

```text
POST /manual-library/rebuild -> task_id
set state.rebuildTask
poll GET /rebuild/{task_id} every 1s
  done -> stop, show success, reload manuals
  failed -> stop, show error, reload manuals
```

The UI should make clear that failed rebuilds preserve the served graph and keep changes pending.

## Styling Direction

- Use a restrained operations-console layout.
- Avoid cards inside cards.
- Use fixed-height top toolbar and responsive table/detail layout.
- On narrow screens, stack table and detail panel.
- Use status badges sparingly:
  - active
  - disabled
  - archived
  - searchable
  - pending rebuild
- Keep button labels short and predictable.
- Avoid decorative gradients/orbs.

## Auth Considerations

The simplest M7 model:

- If `auth.enabled=false`, page calls work anonymously because the API treats anonymous as admin.
- If `auth.enabled=true`, operator pastes an API key into the page token input.
- Store token in `sessionStorage` at most.
- Never render configured keys or secrets server-side.

## Compatibility

- Existing JSON endpoints keep their current shapes.
- Existing API clients are unaffected.
- Static/template additions must not change `/docs`, `/metrics`, `/health`, `/ready`, `/search`, `/manuals`, or `/rebuild`.

## Rollout / Rollback

Rollout:

- Ship UI route alongside existing API.
- Document route in README.

Rollback:

- Remove or disable UI route/static mount. JSON APIs continue to work.

## Open Design Notes

- Jinja2 is not currently declared in `pyproject.toml`; add it if FastAPI does not already provide it transitively in the locked environment.
- HTMX is optional. If used, prefer a local vendored/static file or CDN only if project policy allows network-delivered UI assets. Vanilla JS is the safer default.
