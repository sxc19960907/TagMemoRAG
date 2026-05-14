# Code Context - M27 S3-Compatible Blob Store

Date: 2026-05-14

## Current M26 Implementation Points

- `src/tagmemorag/config.py`
  - `ManualLibraryConfig.blob_backend` already accepts `local | s3`.
  - Existing S3 fields: `s3_bucket`, `s3_prefix`, `s3_endpoint_url`, `s3_region`, `s3_access_key_env`, `s3_secret_key_env`.
  - Missing likely fields: session token env, addressing style, timeout.

- `src/tagmemorag/manual_blob_store.py`
  - Owns `BlobRef`, `ManualBlobStore`, `LocalManualBlobStore`, `create_blob_store()`, key helpers, and content-type guessing.
  - `create_blob_store()` returns local store or raises `INVALID_CONFIG` for S3.
  - Local key shape: `{kb_name}/{manual_id}/{version}/{sha256-prefix}-{safe_basename}`.

- `src/tagmemorag/manual_registry.py`
  - SQLite registry persists `blob_backend`, `blob_key`, checksum, content type, size, and version.
  - Registry is backend-agnostic if `BlobRef` is correct.

- `src/tagmemorag/manual_library.py`
  - Registry mode uses `create_blob_store(cfg).put(...)` before registry upsert.
  - Registry rebuild staging uses `create_blob_store(cfg).get(record.blob_key)`.
  - `verify_registry_blobs()` already calls `exists()` through the blob-store interface.
  - Migration path already reads sidecar source bytes and calls blob-store `put()`.

- `src/tagmemorag/state.py`
  - Registry rebuild staging happens before async rebuild starts and is cleaned up after worker completion.
  - Rebuild failure keeps old graph and dirty state pending.

- `tests/unit/test_manual_blob_store.py`
  - Covers local blob store key safety and round trip.

- `tests/unit/test_manual_library.py`
  - Covers registry mode upload/list/migrate/rebuild.
  - Useful model for adding S3 fake-client tests.

## Dependency Context

- `pyproject.toml` uses optional dependency groups for feature backends:
  - `qdrant = ["qdrant-client>=1.16.1; python_version < '3.13'"]`
- No boto3/botocore dependency currently exists.
- M27 should add an optional `s3` extra rather than a required dependency.

## External API Research

- Official boto3 S3 client docs expose `put_object`, `get_object`, `head_object`, and `delete_object` as the basic operations needed by `ManualBlobStore`.
- Boto3 session/client creation supports `endpoint_url`, which is needed for MinIO and S3-compatible services.
- Boto3 credentials can come from environment variables such as `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN`, or from the default credential chain.
- Botocore `Config` supports S3 `addressing_style` values `auto`, `virtual`, and `path`. Path style is often needed for local MinIO and some compatible endpoints.

References:

- https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/put_object.html
- https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/get_object.html
- https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/head_object.html
- https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/delete_object.html
- https://boto3.amazonaws.com/v1/documentation/api/latest/reference/core/session.html
- https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html
- https://botocore.amazonaws.com/v1/documentation/api/latest/reference/config.html

## Constraints For Implementation

- Default test path must remain offline and local.
- S3 mode should be testable with injected fake clients.
- API/CLI/admin response shapes should stay additive and safe.
- Object-store failures must not clear dirty state or swap active graph.
- No raw document bodies or credentials in logs/errors/audit/debug output.
