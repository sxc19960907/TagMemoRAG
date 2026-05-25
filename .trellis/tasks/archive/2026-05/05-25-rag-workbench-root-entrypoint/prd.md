# Make RAG workbench the browser entrypoint

## Goal

Make the local browser entrypoint obvious for a normal RAG user: opening the server root should lead to the existing RAG Workbench instead of requiring users to know `/admin/rag-workbench`, `/admin/manual-library`, or `/qa`.

## Requirements

- Add a root browser route for `/` that lands on the RAG Workbench for the selected/default KB.
- Preserve existing direct routes for `/admin/rag-workbench`, `/admin/manual-library`, `/admin/retrieval-quality`, and `/qa`.
- Keep API routes and JSON contracts unchanged.
- Keep the implementation minimal and covered by unit tests.
- Do not touch unrelated untracked files (`.codegraph/`, `.mcp.json`).

## Acceptance Criteria

- [ ] `GET /` returns a redirect to `/admin/rag-workbench?kb_name=default` or otherwise loads the same workbench shell.
- [ ] The existing workbench shell route continues to render.
- [ ] Focused UI route tests pass.
- [ ] No normal unit/e2e quality regression is introduced.

## Notes

- Lightweight route-discoverability task; PRD-only planning is sufficient.
