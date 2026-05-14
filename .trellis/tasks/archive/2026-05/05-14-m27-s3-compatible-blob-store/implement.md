# implement.md - M27 S3-Compatible Blob Store

## Implementation Checklist

- [ ] Read backend specs with `trellis-before-dev` before coding.
- [ ] Re-read M26 registry/blob-store docs and current implementation.
- [ ] Curate `implement.jsonl` and `check.jsonl`.
- [ ] Add S3 config fields if needed:
  - `s3_session_token_env`
  - `s3_addressing_style`
  - `s3_timeout_seconds`
- [ ] Add optional `s3` dependency extra with boto3.
- [ ] Implement S3 key helpers:
  - prefix normalization
  - S3 object key generation
  - safe segment/basename reuse
- [ ] Implement `S3ManualBlobStore` behind `ManualBlobStore`.
- [ ] Update `create_blob_store(cfg)` to return S3 backend when configured.
- [ ] Add safe credential/env resolution.
- [ ] Add safe boto3/botocore lazy import and `INVALID_CONFIG` errors.
- [ ] Map S3 client errors into project `ServiceError` without leaking secrets.
- [ ] Add fake-client unit tests for S3 put/get/exists/delete.
- [ ] Add tests for prefix/key safety and content metadata.
- [ ] Add tests for missing dependency/config/credential failure paths.
- [ ] Add registry/manual-library tests for S3-mode upload, replace, migration, verify-blobs, and rebuild staging.
- [ ] Add failure tests:
  - upload failure does not commit registry or dirty state
  - missing S3 object during rebuild preserves old graph and pending dirty state
- [ ] Add env precedence test for S3 config fields.
- [ ] Add optional MinIO integration test profile, skipped by default.
- [ ] Update README with install/config/migration/verify/rollback examples.
- [ ] Update specs if S3 blob-store conventions should become durable backend rules.

## Validation

Focused tests:

```bash
uv run pytest tests/unit/test_manual_blob_store.py tests/unit/test_manual_registry.py tests/unit/test_manual_library.py -q
uv run pytest tests/unit/test_config_env.py tests/unit/test_cli.py -q
```

New/updated tests expected:

```bash
uv run pytest tests/unit/test_manual_s3_blob_store.py -q
uv run pytest tests/unit/test_manual_library.py -q
uv run pytest tests/unit/test_config_env.py -q
```

Default final check:

```bash
uv run pytest tests/ -q
```

Optional MinIO check:

```bash
TAGMEMORAG_MINIO_TEST=1 \
TAGMEMORAG__MANUAL_LIBRARY__BLOB_BACKEND=s3 \
TAGMEMORAG__MANUAL_LIBRARY__S3_ENDPOINT_URL=http://localhost:9000 \
TAGMEMORAG__MANUAL_LIBRARY__S3_BUCKET=tagmemorag-test \
uv run pytest tests/integration/test_manual_s3_blob_store.py -q
```

Only run optional MinIO when explicitly configured.

## Review Gates

- Confirm local mode still works without boto3 installed.
- Confirm `blob_backend=s3` fails clearly when dependency or config is missing.
- Confirm raw credentials never appear in Settings serialization, errors, logs, audit detail, CLI output, or README examples.
- Confirm object keys do not contain absolute paths, traversal, full endpoint URLs, or credentials.
- Confirm upload writes object before registry commit and dirty-state marking.
- Confirm failed upload does not mutate registry or dirty state.
- Confirm rebuild read failure preserves old graph and dirty state.
- Confirm default tests have no live object-storage dependency.
- Confirm optional MinIO tests are skipped unless explicitly enabled.

## Rollback Points

- If optional dependency integration causes broad packaging churn, keep boto3 lazy-loaded and avoid touching local dependency paths.
- If registry migration with S3 becomes too risky, ship S3 blob store plus upload/replace first and keep sidecar-to-S3 migration behind tests until fixed.
- If rebuild staging exposes memory pressure from `get() -> bytes`, defer streaming but document it; do not change parser staging contract in M27 unless required.
- If S3-compatible service quirks appear, support `s3_addressing_style=path` and endpoint URL first; defer provider-specific branches unless backed by tests.
