# Design

## Scope

Add one-time API key generation to the existing People & Access page. The generated key remains config-backed: operators copy the returned config entry into `auth.keys` and give the plaintext key to the client once.

## Shared Generation Helper

Add a small auth helper module that owns generation parity between CLI and API:

- `generate_plaintext_key(prefix: str = "tmr_live_") -> str`
- `build_api_key_config_entry(...) -> dict[str, object]`
- `generate_api_key_material(...) -> dict[str, object]`

The helper uses `secrets.token_urlsafe(24)` and `ConfigAuthStore.hash_plaintext()` to match the CLI's current behavior.

## API Contract

`POST /admin/people/access-keys/generate`

Request:

```json
{
  "id": "support-a",
  "label": "Support A",
  "scopes": ["search"],
  "kb_allowlist": ["default"],
  "rate_limit_per_minute": 100,
  "prefix": "tmr_live_"
}
```

Response:

```json
{
  "schema_version": "people_access_key_generation.v1",
  "plaintext_key": "tmr_live_...",
  "config_entry": {
    "id": "support-a",
    "hash": "sha256:...",
    "label": "Support A",
    "kb_allowlist": ["default"],
    "scopes": ["search"],
    "rate_limit_per_minute": 100
  },
  "config_json": "{...pretty json...}"
}
```

The endpoint uses `Depends(require_scope("admin"))` and `rate_limit_dep`.

## UI

Extend `people_admin.html` and `people_admin.js`:

- Add form fields for id, label, scopes, KB allowlist, rate, and prefix.
- Add a Generate button and one-time result block.
- Render plaintext key and config JSON in separate copyable blocks.
- Keep access table read-only and unchanged.

## Compatibility

The CLI should call the shared helper but keep output text compatible with existing tests.
