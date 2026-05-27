# Auth Role Boundary Trial Review Design

## Scope

This task improves operator clarity around existing auth boundaries. It does not change auth enforcement, token hashing, scope semantics, or public path behavior.

## Current Boundary

- Auth disabled: browser pages and APIs are usable with anonymous admin-like access for local demos.
- Auth enabled: admin APIs require Bearer tokens.
- `admin` scope implies all scopes.
- `search` scope is appropriate for normal Q&A/search/retrieve use.
- People & Access summary and key generation require `admin`.

## UI Hardening

Add an access boundary guide to People & Access so trial operators can see:

- which scope to give a Q&A user;
- which scope can trigger rebuilds;
- which scope is needed for this page;
- that generated plaintext keys are one-time material.

Map common HTTP failures to clearer messages:

- 401: paste an admin Bearer token.
- 403: the token is valid but lacks `admin`; use an admin-scoped key or rotate access.

## Risk Controls

- Do not display key hashes or plaintext from configured keys.
- Do not loosen endpoint dependencies.
- Keep wording as UI guidance only; backend tests continue to prove enforcement.
