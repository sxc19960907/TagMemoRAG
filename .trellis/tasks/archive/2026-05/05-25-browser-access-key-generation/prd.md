# Add browser access key generation

## Goal

Let an admin generate a new config-backed API-key identity from the People & Access browser page, without changing the existing authentication storage model or exposing secrets beyond the one-time response.

## Requirements

- Add a protected browser/API workflow for generating an API key payload from `id`, `label`, `scopes`, `kb_allowlist`, `rate_limit_per_minute`, and optional token prefix.
- Reuse the same hashing and plaintext token shape as the existing `tagmemorag auth generate-key` CLI.
- Return a one-time plaintext key and a config snippet that can be added under `auth.keys`.
- Do not persist the generated key, modify `config.yaml`, reload auth state, log plaintext tokens, or expose generated plaintext anywhere except the immediate API response/UI result.
- Require existing `admin` scope when auth is enabled.
- Keep the UI understandable: form controls should make scopes, KBs, rate limit, and copy targets obvious.
- Keep the existing access summary behavior stable.

## Acceptance Criteria

- [x] `POST /admin/people/access-keys/generate` accepts key generation input and returns `plaintext_key`, safe `config_entry`, and copyable JSON.
- [x] Generated `config_entry.hash` verifies the one-time plaintext key via `ConfigAuthStore`.
- [x] Auth-enabled requests require an admin key; search-only keys are rejected by existing auth dependency behavior.
- [x] People & Access page includes a clear generation form and one-time result area.
- [x] Unit tests cover the endpoint, auth guard, CLI/helper parity, and static UI assets.
- [x] No generated plaintext or hash leaks into access-summary key rows.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
- Out of scope: persisting new keys, revoking/rotating keys, password-based users, user database, audit trail.
