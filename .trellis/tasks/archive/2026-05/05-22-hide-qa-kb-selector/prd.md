# Hide QA knowledge base selector

## Goal

Make the user-facing `/qa` page tenant/KB-agnostic from the user's perspective. Users should not see or manually edit `Knowledge base`, `kb_name`, or `default`; the page should still use the configured KB internally.

## Requirements

- Remove the visible KB input and "Use KB" control from `/qa`.
- Keep `kb_name` as an internal value from server-rendered config/URL/default.
- Keep `/answer` request payload behavior unchanged except it reads `kb_name` from internal state rather than a visible input.
- Keep the left rail useful by showing product/user-facing assistant context instead of internal KB names.
- Keep `/admin/rag-workbench` unchanged as the place where admins can switch KBs.
- Preserve auth token display only when auth is enabled.

## Acceptance Criteria

- [x] `/qa?kb_name=ops` still renders selected KB in page config for internal use.
- [x] `/qa` HTML does not show "Knowledge base", "Use KB", or `id="qa-kb-name"`.
- [x] `qa_page.js` still submits `kb_name` to `/answer`.
- [x] KB URL query param is preserved internally but not exposed as an editable user control.
- [x] Focused UI tests pass and assert the KB selector is hidden on `/qa`.

## Notes

- Lightweight task: PRD-only is sufficient because this is a UI simplification over an existing route and API contract.
