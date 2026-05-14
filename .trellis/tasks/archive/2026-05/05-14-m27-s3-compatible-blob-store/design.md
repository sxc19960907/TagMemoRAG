# design.md - M27 S3-Compatible Blob Store

## Scope

M27 implements the S3-compatible backend promised by the M26 blob-store boundary. It does not change parser behavior, graph/vector persistence, Qdrant sync, ranking, auth, or admin UI workflows. It should be a storage-backend swap behind `ManualBlobStore`, not a rewrite of managed-library APIs.

## Current M26 Boundary

```text
manual_library.upsert_manual()
  -> validate metadata
  -> create_blob_store(cfg).put(...)
  -> create_registry(...).upsert(...)
  -> mark_dirty(...)

registry-backed rebuild
  -> materialize_registry_build_source()
     -> registry.list(kb)
     -> create_blob_store(cfg).get(record.blob_key)
     -> write staging/{source_file}
     -> write staging sidecar
  -> existing build path
```

This is the right integration point for S3. M27 should update `create_blob_store(cfg)` to return an S3 implementation when `manual_library.blob_backend == "s3"`.

## Target Architecture

```text
ManualBlobStore protocol
  ├── LocalManualBlobStore
  └── S3ManualBlobStore
       ├── boto3/botocore client adapter
       ├── key builder / prefix normalizer
       ├── safe error mapping
       └── fake-client-friendly constructor for tests
```

The registry remains the source of truth for manual metadata and blob references. S3 owns only original uploaded bytes and safe object metadata.

## Dependency Design

Add an optional extra:

```toml
[project.optional-dependencies]
s3 = [
    "boto3>=1.34",
]
```

Runtime behavior:

- Import boto3 lazily inside S3 client creation.
- If missing and `blob_backend=s3`, raise:

  ```json
  {
    "code": "INVALID_CONFIG",
    "message": "boto3 is required when manual_library.blob_backend=s3.",
    "detail": {"dependency": "boto3", "extra": "s3"}
  }
  ```

- Default/local code paths must not import boto3.

This mirrors the optional Qdrant pattern and avoids making local development heavier.

## Configuration Contract

Existing M26 fields:

```yaml
manual_library:
  blob_backend: s3
  s3_bucket: tagmemorag-manuals
  s3_prefix: manuals/prod
  s3_endpoint_url: http://localhost:9000
  s3_region: us-east-1
  s3_access_key_env: MINIO_ROOT_USER
  s3_secret_key_env: MINIO_ROOT_PASSWORD
```

Recommended additions:

```yaml
manual_library:
  s3_session_token_env: AWS_SESSION_TOKEN
  s3_addressing_style: path  # auto | virtual | path
  s3_timeout_seconds: 10
```

Rules:

- `s3_bucket` is required for S3 mode.
- `s3_region` may default to `us-east-1` for MinIO/local compatibility if unset.
- `s3_endpoint_url` is optional for AWS S3 and required for many compatible services.
- When `s3_access_key_env` and `s3_secret_key_env` are non-empty, read credentials from those env vars.
- If explicit env names are blank, allow boto3’s default credential chain.
- Do not store actual credential values in Settings, registry, audit events, logs, metrics, traces, or API responses.
- Use env override names such as:
  - `TAGMEMORAG__MANUAL_LIBRARY__BLOB_BACKEND=s3`
  - `TAGMEMORAG__MANUAL_LIBRARY__S3_BUCKET=tagmemorag-manuals`
  - `TAGMEMORAG__MANUAL_LIBRARY__S3_ENDPOINT_URL=http://localhost:9000`

## Client Creation

Use boto3’s client creation with explicit endpoint support:

```python
client = boto3.client(
    "s3",
    endpoint_url=cfg.manual_library.s3_endpoint_url or None,
    region_name=cfg.manual_library.s3_region or "us-east-1",
    aws_access_key_id=access_key_or_none,
    aws_secret_access_key=secret_key_or_none,
    aws_session_token=session_token_or_none,
    config=Config(
        connect_timeout=cfg.manual_library.s3_timeout_seconds,
        read_timeout=cfg.manual_library.s3_timeout_seconds,
        retries={"mode": "standard", "total_max_attempts": 3},
        s3={"addressing_style": cfg.manual_library.s3_addressing_style},
    ),
)
```

For tests, `S3ManualBlobStore` should accept an injected client object with `put_object`, `get_object`, `head_object`, and `delete_object` methods. This avoids network and keeps default tests deterministic.

## Object Key Strategy

Use object keys that are safe, deterministic, and stable:

```text
{normalized_prefix}/{safe_kb_name}/{safe_manual_id}/{version}/{sha256-prefix}-{safe_basename}
```

Examples:

```text
manuals/prod/default/cm1/1/9f86d081884c7d65-cm1.md
default/cm1/1/9f86d081884c7d65-cm1.md
```

Rules:

- Strip leading/trailing slashes from prefix.
- Collapse duplicate slashes.
- Reject or normalize `.` / `..` path components.
- Reuse existing `_safe_segment` and `_safe_basename` logic where possible.
- `blob_key` in registry is the object key only, not `s3://bucket/key`.
- Bucket remains config, not registry state. Registry stores `blob_backend="s3"` plus object key.

Rationale:

- Keeps registry references portable between compatible endpoints that share bucket/prefix config.
- Avoids leaking deployment-specific URLs.
- Matches M26 local shape closely enough for operator familiarity.

## Operation Semantics

### put

1. Compute SHA-256 checksum and content length from bytes.
2. Build object key using kb/manual/version/checksum/source file.
3. Call `put_object` with:
   - `Bucket`
   - `Key`
   - `Body`
   - `ContentType`
   - safe `Metadata`
4. Return `BlobRef(backend="s3", blob_key=key, checksum=..., size_bytes=..., content_type=...)`.

Use project checksum as the source of truth instead of relying on ETag because ETag is not a universal content MD5 for multipart uploads or all S3-compatible services.

### get

1. Call `get_object(Bucket, Key)`.
2. Read `response["Body"].read()`.
3. Return bytes.
4. Map not-found and access/client errors to `ServiceError` with safe details.

### exists

1. Call `head_object(Bucket, Key)`.
2. Return `True` on success.
3. Return `False` for 404/NoSuchKey/NotFound.
4. Raise `ServiceError` for auth, timeout, endpoint, or other client failures.

### delete

1. Call `delete_object(Bucket, Key)`.
2. Treat not-found as success if the client returns success; if explicit 404 appears, keep delete idempotent.
3. Raise `ServiceError` for unsafe client/config failures.

## Error Mapping

Recommended mapping:

| Condition | Project Error |
|-----------|---------------|
| boto3/botocore missing | `INVALID_CONFIG` |
| missing bucket | `INVALID_CONFIG` |
| missing explicit credential env var | `INVALID_CONFIG` |
| invalid blob key | `INVALID_INPUT` |
| object missing during `get` | `STORAGE_LOAD_FAILED` |
| endpoint/auth/client failure during `put/get/head/delete` | `STORAGE_LOAD_FAILED` or `INVALID_CONFIG` depending on cause |

Details may include only safe fields:

- `blob_backend`
- `bucket`
- `blob_key`
- `endpoint_url_present`
- `operation`
- `error_code`

Details must not include:

- access key / secret / token
- signed URL
- request headers
- raw document body
- stack trace

## Registry Transaction Safety

The existing M26 order is correct:

```text
blob_store.put(...)
registry.upsert(...)
mark_dirty(...)
```

M27 should preserve this. If object upload fails, no registry row is created or updated and dirty state is not marked. For file replacement, the previous registry blob remains active until the new object put and registry update both succeed.

Potential orphan case:

- Object upload succeeds but registry update fails.

MVP handling:

- Log only safe operation/error fields.
- Do not delete immediately unless implementation can do so safely without masking the registry error.
- Document that `verify-blobs` checks missing references, not orphan cleanup.
- Defer orphan sweeping to M30 import/export or a future maintenance task unless trivial.

## Migration Compatibility

When registry mode uses `blob_backend=s3`, existing M26 migration should:

```text
scan sidecars -> read local source bytes -> s3.put -> registry.upsert
```

Idempotency:

- If registry record already exists, skip it.
- If source sidecar exists but object missing for an existing registry row, `verify-blobs` reports missing; migration should not silently mutate the existing row unless an explicit repair mode is later added.

Dry run:

- Must not upload objects.
- Should report how many records would upload/import.

## Rebuild Compatibility

Registry-backed rebuild already calls `blob_store.get(record.blob_key)`. S3 mode should use the same staging tree:

```text
S3 object bytes -> temporary local source_file -> sidecar from registry -> build_kb()
```

Failure behavior:

- Missing object or failed read raises before graph swap.
- Rebuild task status becomes failed.
- Old `GraphState` remains active.
- Dirty state stays pending.
- Staging cleanup still runs.

## CLI / API Compatibility

Existing CLI commands should be enough for MVP:

```bash
python -m tagmemorag manual-library registry inspect --kb default
python -m tagmemorag manual-library registry migrate --kb default --dry-run
python -m tagmemorag manual-library registry migrate --kb default
python -m tagmemorag manual-library registry verify-blobs --kb default
python -m tagmemorag manual-library rebuild --kb default
```

If implementation adds `manual-library registry probe`, it should only check safe connectivity and bucket access; no object listing is required for MVP.

API/admin response additions should remain additive and safe. Prefer:

- `storage_backend`
- `blob_ref_present`
- `size_bytes`
- `content_type`
- `registry_backend`
- `registry_version`

Do not expose signed URLs or raw endpoint credential data.

## Testing Strategy

### Fake client unit tests

Create a small in-memory fake:

```python
class FakeS3Client:
    objects: dict[tuple[str, str], dict[str, Any]]
    def put_object(...)
    def get_object(...)
    def head_object(...)
    def delete_object(...)
```

Use it to test all blob-store behavior without boto3 or network.

### Botocore/client error tests

If botocore is installed in the S3 extra test environment, simulate `ClientError` shapes. If not, keep adapter error handling testable through generic exception objects or small fake exception classes.

### Registry/manual-library tests

- Registry upload in S3 mode stores `blob_backend=s3` and object key.
- Replace writes new object/version and leaves old record active on failed put.
- Migration dry-run does not upload.
- Migration commit uploads and creates registry row.
- `verify-blobs` reports missing object after fake deletion.
- Rebuild from fake S3 produces identical manual ids/chunk metadata to local registry mode.
- Missing object during rebuild keeps pending dirty state and old graph.

### Optional MinIO integration

Add an opt-in test marked or skipped unless env vars are present:

```text
TAGMEMORAG_MINIO_TEST=1
TAGMEMORAG__MANUAL_LIBRARY__S3_ENDPOINT_URL=http://localhost:9000
TAGMEMORAG__MANUAL_LIBRARY__S3_BUCKET=tagmemorag-test
MINIO_ROOT_USER=...
MINIO_ROOT_PASSWORD=...
```

Default `uv run pytest tests/ -q` must skip it.

## Rollout

1. Ship code with `blob_backend=local` default.
2. Install S3 extra in a development environment.
3. Start MinIO or configure a test bucket.
4. Enable:

   ```yaml
   manual_library:
     registry_backend: sqlite
     blob_backend: s3
   ```

5. Dry-run sidecar migration.
6. Commit migration.
7. Verify blobs.
8. Rebuild and compare search behavior.
9. Roll out to production with bucket backup/lifecycle policy managed outside TagMemoRAG.

## Rollback

- If upload path fails before registry update, no rollback action is needed because no new record becomes active.
- If rebuild from S3 fails, switch `blob_backend` back only if registry rows reference local blobs; otherwise restore object storage availability and retry.
- If migration from local sidecars to S3 fails midway, rerun migration after fixing config; existing registry rows are skipped.
- For deployments that migrated from sidecars without deleting local files, operators can switch `registry_backend=file` to rebuild from original local sidecars.
- Do not delete local sidecars as part of M27 migration.

## Follow-Up Milestones

- M28: background rebuild queue/retry/cancellation around object-store transient failures.
- M29: admin UI for registry/audit/blob diagnostics.
- M30: import/export bundles and orphan/blob repair tools.
- M31: production deployment guide with object-store backup and restore playbooks.
