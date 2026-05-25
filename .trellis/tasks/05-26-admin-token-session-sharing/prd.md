# Share admin API token across pages

## Goal

Make browser-based admin pages feel like one coherent console by sharing the API token within the current browser session. Operators should not need to paste the same bearer token separately on RAG Workbench, People & Access, Retrieval Quality, Manual Library, and QA.

## Requirements

- Reuse the existing `sessionStorage` key `tagmemoragApiToken` across admin/browser pages.
- Load the saved token into each page's API token input on startup.
- Persist token changes from each page back to `sessionStorage`; remove it when the field is cleared.
- Keep token storage session-scoped only; do not introduce localStorage, cookies, backend persistence, logs, or URL parameters.
- Preserve existing Authorization header behavior and page-specific request flows.
- Add a tiny shared static helper instead of duplicating token persistence logic in every page.

## Acceptance Criteria

- [x] Workbench, People & Access, Retrieval Quality, Manual Library, and QA all load the shared session token into their token fields.
- [x] Updating or clearing any token field updates the shared session token.
- [x] Existing request header behavior still sends `Authorization: Bearer <token>` when a token is present.
- [x] Unit/static tests cover the helper and representative page wiring.
- [x] No token is stored in localStorage, cookies, backend state, logs, or URLs.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
- Out of scope: login UI, token refresh, persistent account sessions, server-side session management.
