# RAG User Readiness Dashboard Design

## Backend Boundary

Add an API-layer helper module `api_rag_readiness.py`. It may depend on existing API-layer helpers and domain state, but it will not import frontend code or mutate state.

Main function:

```python
rag_readiness_summary(kb_name, *, settings, app_state, api_key, get_rebuild_queue) -> dict[str, object]
```

Route:

- `GET /admin/rag-readiness/summary?kb_name=<kb>`
- Scope: `admin`

The endpoint returns a bounded UI contract:

```json
{
  "schema_version": "rag_readiness.v1",
  "kb_name": "default",
  "status": "ready|needs_review|not_ready",
  "cards": [...],
  "actions": [...]
}
```

Cards are normalized as:

```json
{
  "id": "kb|manuals|eval|qa",
  "title": "KB Loaded",
  "status": "ready|needs_review|not_ready|unknown",
  "summary": "...",
  "detail": {"bounded": "values"}
}
```

Actions are normalized as:

```json
{
  "label": "Open Q&A",
  "href": "/qa?kb_name=default",
  "kind": "primary|secondary|warning"
}
```

## Signal Sources

- KB/process card uses `app_state.embedder_ready`, `app_state.is_shutting_down`, and `app_state.kbs.get(kb_name)`.
- Manual card reuses `api_manual.manual_library_diagnostics(...)` with `verify_blobs=False` and `include_jobs=True`.
- Eval card reuses `api_eval_runs.list_eval_suites(settings=settings)` and finds suites whose latest report includes the selected KB where possible; otherwise it reports fixture/global latest browser eval state.
- QA card is derived from KB readiness and links to `/qa` and `/admin/rag-workbench`.

## Status Rules

Overall status:

- `not_ready` if process is shutting down, embedder is not ready, or selected KB is not loaded.
- `needs_review` if manual diagnostics show pending changes, failed rebuild jobs, missing blobs, or the latest browser eval failed.
- `ready` if loaded and no blocking/review signals are present.

If no eval report exists, that is `needs_review` rather than `not_ready`: Q&A may work, but the user has not verified quality recently.

## Frontend

Add:

- `web/templates/rag_readiness.html`
- `web/static/rag_readiness.js`

The page follows existing admin-page conventions: topbar, KB selector, token input, top-action links, status strip, cards, and next actions. It is read-only and browser-first.

## Compatibility

Existing routes and API contracts remain unchanged. New summary schema is additive and isolated under `/admin/rag-readiness/summary`.

## Safety

The summary returns counts, statuses, build ids, timestamps, report paths, and route links only. It does not include raw report cases, raw queries, raw answer text, document snippets, vectors, or secrets.
