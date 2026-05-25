# Improve admin people management page

## Goal

Make backend personnel/access management easier for an operator to understand from the browser. The current system uses config-backed API keys rather than database users, so this task adds a clear People & Access admin view for safe access overview without changing the authentication storage model.

## Requirements

- Add a browser page for backend personnel/access management at an admin URL.
- Show the current auth posture: enabled/disabled, backend type, global rate limit, public paths, active keys, revoked keys, and admin-capable keys.
- Show each configured API-key identity as a person/access row with safe fields only: id, label, scopes, KB allowlist, per-key rate limit, created time, last used time, and active/revoked status.
- Never expose plaintext tokens, API-key hashes, Authorization headers, or other secrets in API responses, HTML, logs, or tests.
- Protect the access summary endpoint with the existing `admin` scope when auth is enabled.
- Keep the first iteration read-only and guided. Include clear operator hints for generating/configuring keys, but do not add create/revoke/rotate actions yet.
- Link the page from the existing RAG Workbench navigation so browser users can discover it.
- Reuse the current admin shell and static asset conventions.

## Acceptance Criteria

- [x] `/admin/people` serves a browser shell with People & Access navigation, token field, summary area, key table, and detail panel.
- [x] A JSON endpoint returns a safe personnel/access summary without `hash` or plaintext secret material.
- [x] Auth-enabled requests require an API key with `admin` scope for the summary endpoint; non-admin keys are rejected by the existing auth dependency behavior.
- [x] The RAG Workbench links to the new People & Access page while preserving the selected KB in the URL.
- [x] Empty/disabled auth states are understandable in the UI.
- [x] Unit tests cover the browser shell, static asset, safe API payload, and admin-scope guard.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
- Out of scope: user database, password login, CRUD key management, key rotation workflow, persistent `last_used_at` storage.
