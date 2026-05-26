# Design

## Scope

Extend the existing People & Access browser UI with lifecycle guidance for config-backed API keys. This remains a client-side operational aid; it does not mutate auth state.

## UI Behavior

When an access identity is selected:

- Show a lifecycle section in the detail pane.
- `Use as template` copies `label`, `scopes`, `kb_allowlist`, and `rate_limit_per_minute` into the generate form and proposes `<id>-replacement`.
- Revoke snippet displays a safe config entry with id/label/scopes/kb/rate and `revoked: true`, but no original hash.
- Rotate plan summarizes: generate replacement, add generated config entry, deploy/reload config, then mark old key revoked.

When no identity is selected:

- Lifecycle section shows a neutral empty state.

## Data Flow

The UI uses only the safe `/admin/people/access-summary` payload already returned by the backend. No new backend route is required.

## Compatibility

No changes to auth verification, config format, key generation API, or CLI behavior.
