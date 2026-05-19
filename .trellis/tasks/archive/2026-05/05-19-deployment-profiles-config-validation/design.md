# Deployment Profiles And Config Validation — Design

## Boundary

This task is operator ergonomics, not runtime behavior change. It adds:

- static example YAML files under a small examples directory
- a `tagmemorag config validate` CLI branch
- a helper module that converts `Settings` into a safe validation report

It does not change server startup, storage schemas, or API response contracts.

## CLI Contract

```bash
tagmemorag config validate --config config.yaml
```

Optional flags:

- `--format json` only for this task; reserve text/table output for later.
- No live probe flag in this task.

Exit mapping:

- `0` for `passed` or `warning`
- `1` for `failed`
- `2` only for invalid CLI usage or config parse exceptions that argparse/Pydantic already surface

## Report Contract

```json
{
  "schema_version": "config_validation.v1",
  "status": "passed",
  "config_path": "config.yaml",
  "profile": {
    "model_provider": "hashing",
    "vector_store": "npz",
    "registry_backend": "file",
    "blob_backend": "local"
  },
  "checks": [
    {"name": "config_load", "status": "passed", "detail": {}}
  ]
}
```

Check statuses: `passed`, `warning`, `failed`.

Details are safe and bounded: env var names, dependency names, provider names, local path field names, and booleans. Do not emit secret values, raw config dumps, file inventories, raw document text, vectors, or stack traces.

## Validation Rules

Pass/fail:

- Config loads via `load_config()`.
- Local path checks create missing directories or verify parent writability for:
  - `storage.data_dir`
  - `manual_library.root_dir`
  - `manual_library.blob_root_dir` when `blob_backend=local`
  - parent of `manual_library.registry_path` when `registry_backend=sqlite`
  - `assets.root_dir` when `assets.enabled` and store is local
- `manual_library.blob_backend=s3` requires `s3_bucket`.
- `model.provider=http` requires the env var named by `model.api_key_env`.
- `reranker.enabled=true` with provider `siliconflow` requires `reranker.api_key_env`.
- `answer.enabled=true` with provider `openai_compatible` requires `answer.api_key_env`.

Warnings:

- `vector_store.provider=qdrant` but `qdrant_client` import is unavailable.
- `manual_library.blob_backend=s3` but `boto3` import is unavailable.
- `auth.enabled` and metrics are enabled but metrics path is missing from public auth paths.
- `answer.enabled=false` when validating an answer profile should be handled by profile content/tests rather than validator special-casing.

## Example Profiles

Use `examples/config/`:

- `local-hashing-npz.yaml`
- `local-sqlite-registry.yaml`
- `qdrant.yaml`
- `s3-blob.yaml`
- `answer-openai-compatible.yaml`

Profiles should be partial YAML snippets that can be passed directly to `--config`. They should prefer relative local paths and env var names, never secret values.

## Rollback

Revert the helper module, CLI parser branch, tests, docs, and example YAML files. No data migration is involved.
