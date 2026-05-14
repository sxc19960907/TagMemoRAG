# M27 S3-Compatible Blob Store

## Goal

Implement an S3-compatible backend behind the M26 `ManualBlobStore` interface so managed manual uploads can store original document bytes in MinIO, AWS S3, Cloudflare R2, Alibaba OSS S3-compatible endpoints, or similar object-storage services. M27 should preserve the local disk default, keep registry-backed manual APIs stable, and make object storage opt-in through configuration and environment-provided credentials.

## Background / Known Context

- M26 introduced `manual_blob_store.py` with `BlobRef`, `ManualBlobStore`, `LocalManualBlobStore`, and `create_blob_store(cfg)`.
- M26 introduced `manual_library.registry_backend=sqlite` and `manual_library.blob_backend=local|s3` config fields, but `blob_backend=s3` currently raises `INVALID_CONFIG`.
- M26 registry records already persist `blob_backend`, `blob_key`, `checksum`, `content_type`, `size_bytes`, and version data.
- Registry-backed rebuild already stages active records by calling `blob_store.get(record.blob_key)`, so a correct S3 backend should require little or no rebuild API change.
- Current managed-library APIs and CLI commands already expose safe storage metadata additively.
- The project has an optional dependency pattern for Qdrant (`uv sync --extra qdrant`); S3 client dependencies should follow the same spirit.
- Safety posture still applies: no raw document bodies, secrets, full local absolute paths, raw credentials, vectors, or high-cardinality machine paths in logs, metrics, debug metadata, traces, audit detail, or API errors.

## Problem

The M26 registry/blob-store architecture is production-shaped but still local-only. Production deployments need object storage because:

- API replicas and rebuild workers should not rely on a shared local filesystem for uploaded source manuals.
- MinIO/local S3-compatible storage is a common deployment pattern for Docker Compose and on-prem installations.
- AWS S3, R2, OSS, and compatible services are the natural durable store for original uploaded documents.
- Operators need a way to verify registry blob references against object storage before rebuilds or disaster recovery.
- Object-storage failures should not corrupt registry state, clear dirty state, or swap the active graph.

## Requirements

### 1. Preserve Defaults And Backward Compatibility

- `manual_library.blob_backend` remains `local` by default.
- Existing file-sidecar mode and local registry mode continue to work without installing boto3, running MinIO, using Docker, or setting credentials.
- Existing default tests must not require live S3, MinIO, network access, or external credentials.
- Existing managed manual API, bulk import, registry migration, dirty-state, and rebuild semantics remain stable.

### 2. S3-Compatible Blob Store

- Add an S3-compatible implementation of `ManualBlobStore`.
- Minimum operations:
  - `put(kb_name, manual_id, source_file, content, metadata) -> BlobRef`
  - `get(blob_key) -> bytes`
  - `delete(blob_key)`
  - `exists(blob_key)`
- `BlobRef.backend` should be `"s3"` for S3-compatible objects.
- `blob_key` should be an object key, not a full URL and not a credential-bearing string.
- Object keys must be deterministic and safe:
  - Use the same logical shape as local blobs where possible: `{prefix}/{kb_name}/{manual_id}/{version}/{sha256-prefix}-{safe_basename}`.
  - Normalize configured prefixes so duplicate slashes and leading slashes do not produce surprising keys.
  - Never include absolute local paths or raw uploaded filename path traversal components.
- Store object metadata safely where practical:
  - checksum
  - manual id
  - source filename basename or safe relative source file
  - content type
  - version
- Do not store raw document text or secrets in object metadata.

### 3. Configuration And Credentials

- Use existing config namespace:
  - `manual_library.blob_backend: local | s3`
  - `manual_library.s3_bucket`
  - `manual_library.s3_prefix`
  - `manual_library.s3_endpoint_url`
  - `manual_library.s3_region`
  - `manual_library.s3_access_key_env`
  - `manual_library.s3_secret_key_env`
- Add fields only if implementation genuinely needs them, such as:
  - `manual_library.s3_session_token_env`
  - `manual_library.s3_addressing_style: auto | virtual | path`
  - `manual_library.s3_timeout_seconds`
- Credentials must be read from environment variables named by config, or from the default boto3 credential chain when explicit env names are blank.
- Raw access keys, secret keys, and session tokens must never be stored in YAML, registry rows, audit events, logs, metrics, traces, API responses, or debug output.
- Missing required S3 config or credentials should raise `INVALID_CONFIG` with safe details.

### 4. Dependency Strategy

- Add S3 client support as an optional extra, for example:

  ```toml
  [project.optional-dependencies]
  s3 = ["boto3>=..."]
  ```

- If `manual_library.blob_backend=s3` and the optional client dependency is missing, fail with `INVALID_CONFIG` and a clear install hint.
- Do not make boto3 a required dependency for local/default users unless implementation evidence shows the optional path is too brittle.

### 5. Registry And Rebuild Compatibility

- Registry-backed upload and file replacement should write object bytes before committing registry state.
- If S3 upload fails, registry records and dirty state must not be updated for that failed mutation.
- Registry-backed rebuild should stage from S3 through the existing `blob_store.get()` path.
- Failed S3 reads during rebuild must leave dirty state pending and preserve the old active graph.
- Blob verification CLI should work for S3-backed records without exposing secrets.
- Migration from local sidecars into registry with `blob_backend=s3` should upload object bytes and create registry records idempotently.

### 6. Operational CLI And Diagnostics

- Existing commands should work in S3 mode:
  - `manual-library registry migrate`
  - `manual-library registry verify-blobs`
  - `manual-library registry inspect`
  - `manual-library rebuild`
- Add CLI diagnostics only if needed, such as a concise object-store probe, but avoid scope creep into a full object browser.
- Diagnostic output may include:
  - backend
  - bucket
  - normalized prefix
  - configured endpoint host or endpoint-present flag
  - checked count
  - missing count
  - safe object keys for missing registry blobs
- Diagnostic output must not include raw credentials, signed URLs, request headers, or document content.

### 7. Testing

- Unit tests should use a fake S3 client or botocore stubs and must not require network access.
- Tests should cover:
  - object key generation and prefix normalization
  - put/get/exists/delete happy path
  - checksum/content type/size metadata
  - missing object maps to false for `exists`
  - missing object in `get` raises a project `ServiceError`
  - upload failure does not create registry row or dirty state
  - rebuild staging failure from missing S3 object preserves old graph and pending dirty state
  - env override for S3 config
  - missing optional dependency/config/credentials errors
- Optional integration tests may target MinIO, but must be skipped unless explicit environment variables or markers are present.

### 8. Documentation

- README should document:
  - local remains default
  - installing S3 extra
  - MinIO development example
  - AWS S3 / R2 / OSS-compatible config shape
  - environment credential variables
  - migration from sidecars into registry-backed S3
  - verification and rollback
- Do not document raw secrets inline except placeholder names.

## Acceptance Criteria

- [ ] A Trellis design exists for S3 object-key strategy, client creation, credential handling, error mapping, migration/rebuild compatibility, tests, rollout, and rollback.
- [ ] `manual_library.blob_backend=local` remains the default and existing default tests pass without boto3, MinIO, Docker, network, or credentials.
- [ ] `manual_library.blob_backend=s3` creates an S3-compatible blob store when optional dependency and config are available.
- [ ] Upload, replace, migration, verify-blobs, and registry-backed rebuild work through the S3 backend.
- [ ] S3 upload failure does not commit registry rows or dirty-state changes.
- [ ] S3 rebuild read failure preserves the old graph and leaves dirty state pending.
- [ ] Missing dependency/config/credential cases raise `INVALID_CONFIG` with safe detail.
- [ ] CLI/API/admin responses expose only safe object-storage metadata.
- [ ] Focused unit tests cover S3 blob-store behavior, registry integration, migration, rebuild failure safety, and config/env precedence.
- [ ] Optional MinIO tests are explicitly opt-in and skipped by default.
- [ ] README documents setup, migration, verification, and rollback.

## Definition of Done

- Planning docs are complete before implementation starts.
- Implementation uses M26 `ManualBlobStore` and registry contracts rather than adding S3-specific branches in API handlers.
- Unit tests and relevant integration/e2e tests pass.
- Full `uv run pytest tests/ -q` passes in the default environment.
- Documentation includes local-default, S3-mode, MinIO-dev, credential, verification, and rollback guidance.

## Out of Scope For M27 MVP

- Direct browser presigned uploads.
- Multipart upload for very large manuals unless needed by tests or common client limits.
- Bucket creation, bucket policy management, lifecycle policy management, or IAM provisioning.
- Object lock, legal hold, KMS key management, or customer-managed encryption UX beyond passing through documented future config.
- Import/export bundles; this belongs to M30.
- Background rebuild queues/cancellation; this belongs to M28.
- Admin UI object browser or audit timeline UI; this belongs to M29.

## Research References

- `.trellis/tasks/05-14-m26-manual-registry-blob-storage/`
- `src/tagmemorag/manual_blob_store.py`
- `src/tagmemorag/manual_registry.py`
- `src/tagmemorag/manual_library.py`
- `src/tagmemorag/config.py`
- `tests/unit/test_manual_blob_store.py`
- `tests/unit/test_manual_registry.py`
- `tests/unit/test_manual_library.py`
- Official boto3 S3 client docs for `put_object`, `get_object`, `head_object`, `delete_object`
- Official boto3/botocore docs for `endpoint_url`, credentials, and S3 addressing style
