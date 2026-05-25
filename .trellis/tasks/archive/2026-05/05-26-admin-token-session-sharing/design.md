# Design

## Scope

Add a shared browser-session API token helper and wire existing browser pages to it. This is a frontend-only ergonomics improvement.

## Helper

Add `admin_token.js` under the existing static directory:

- `sharedApiToken()` reads `sessionStorage["tagmemoragApiToken"]` safely.
- `setSharedApiToken(value)` writes/removes the same key safely.
- `bindSharedApiToken(input)` initializes an input and stores future changes.
- `authHeadersFromToken(value)` returns `{ Authorization: "Bearer ..." }` or `{}`.

The helper catches storage errors so private browsing or disabled storage does not break pages.

## Page Wiring

- Manual Library keeps the same storage key but imports the helper.
- RAG Workbench, People & Access, Retrieval Quality, and QA call `bindSharedApiToken` on startup.
- Header construction reads from the input value, preserving current behavior.

## Compatibility

No backend changes, no auth contract changes, and no token persistence beyond `sessionStorage`.
