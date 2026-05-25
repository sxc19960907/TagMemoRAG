# Design

## Scope

Add a read-only People & Access admin page backed by the existing config-auth store. The UI treats each configured API key as an access identity because TagMemoRAG currently has no user database.

## Routes

- `GET /admin/people` renders `people_admin.html`.
- `GET /admin/people/access-summary` returns a safe JSON summary and uses `Depends(require_scope("admin"))` plus `rate_limit_dep`.

The existing static mount remains `/static/manual-library`; the new JS and CSS additions live under the existing web static directory to match the other admin tools.

## API Contract

Response shape:

```json
{
  "schema_version": "people_access.v1",
  "auth_enabled": true,
  "backend": "config",
  "global_max_rate_limit_per_minute": 1000,
  "public_paths": ["/health", "/metrics"],
  "keys": [
    {
      "id": "support-a",
      "label": "Support A",
      "scopes": ["search"],
      "kb_allowlist": ["default"],
      "rate_limit_per_minute": 100,
      "created_at": "2026-05-25T00:00:00Z",
      "last_used_at": null,
      "revoked": false,
      "status": "active",
      "is_admin": false
    }
  ],
  "summary": {
    "total_keys": 1,
    "active_keys": 1,
    "revoked_keys": 0,
    "admin_keys": 0
  }
}
```

The endpoint must construct this payload from `app_state.auth_store.list_keys()` when available. It must not serialize `ApiKey.hash`.

## UI Shape

- Use the existing topbar with KB input, API token field, and navigation links.
- Summary cards show auth mode, active keys, admin keys, and public paths.
- Main pane shows a dense table for all access identities.
- Detail pane shows the selected identity and a short operator command for generating a new key.
- Empty and disabled auth states render as normal states, not errors.

## Compatibility

No changes to auth verification, config format, CLI key generation, or storage semantics. `last_used_at` remains in-memory for config auth.
