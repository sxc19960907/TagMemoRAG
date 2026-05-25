# Add access key lifecycle guidance

## Goal

Make the People & Access page useful for day-2 API key lifecycle work under the current config-backed auth model: admins should be able to select an existing key, understand how to revoke or rotate it safely, and reuse its permissions when generating a replacement key.

## Requirements

- Add lifecycle guidance for the selected access identity without pretending the system can persist online changes.
- Show a copyable revoke config entry for the selected key with `revoked: true`.
- Show a copyable rotate plan that preserves the selected key's scopes, KB allowlist, and rate limit while using a new id.
- Add a "Use as template" action that pre-fills the generation form from the selected key.
- Keep plaintext tokens, hashes, and existing safe-summary boundaries unchanged.
- Keep the UI browser-first and easy to understand for operators.

## Acceptance Criteria

- [x] Selecting a key displays lifecycle actions for revoke and rotate in the detail pane.
- [x] The revoke config entry is copyable and includes `revoked: true` without exposing the original hash.
- [x] The rotate plan preserves scopes, KB allowlist, and rate limit and points admins to generate a replacement key.
- [x] "Use as template" pre-fills the generation form from the selected key with a replacement id.
- [x] Existing empty/disabled auth states still render cleanly.
- [x] Unit/static tests cover the lifecycle UI assets and helper behavior.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
- Out of scope: online persistence, direct config-file edits, key deletion, audit trail, database-backed users.
