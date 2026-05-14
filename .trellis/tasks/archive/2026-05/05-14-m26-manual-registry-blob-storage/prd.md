# M26 Manual Registry and Pluggable File Storage

## Goal

Move managed manual uploads from a purely local-directory model toward a production-ready storage architecture. M26 should introduce a durable manual registry and a pluggable document blob-store boundary while preserving the current local file workflow as the default. The end state should make it possible to run TagMemoRAG with local disk in development, then switch to S3-compatible object storage such as MinIO, AWS S3, Cloudflare R2, or compatible OSS backends without rewriting upload, rebuild, or admin UI flows.

## Background / Known Context

- Today uploaded manuals are written under `manual_library.root_dir/{kb_name}`.
- Metadata is stored as sidecar files named `*.metadata.json`.
- `build_kb()` scans a local docs directory, calls `load_manual_metadata()`, and parses files directly from disk.
- Managed-library operations such as upload, metadata update, file replacement, disable/archive/delete, dirty state, incremental rebuild, bulk import, tag suggestions, and admin UI all assume local source files and sidecars.
- Qdrant/vector persistence is already abstracted separately. M26 is about original uploaded document storage and manual registry metadata, not vector storage.
- The project already supports SQLite as an auth backend option; using standard-library `sqlite3` for a registry is plausible and avoids a heavy dependency.
- Safety posture from prior milestones still applies: no raw document bodies, secrets, raw query text, vectors, or high-cardinality machine paths in logs, metrics, debug metadata, traces, or admin status fields.

## Problem

Local upload storage is simple and useful, but it limits production deployments:

- Multiple API replicas cannot safely share uploaded files unless they mount the same filesystem.
- Rebuild workers and API servers are tightly coupled to local paths.
- Backups and migration are ad hoc.
- Audit history is limited to the current manifest/dirty state and file timestamps.
- Deleting or overwriting files can lose operator history.
- Future import/export and disaster recovery need stable manual records and blob identities.

## Requirements

### 1. Preserve Current Local Behavior

- Local disk remains the default storage backend.
- Existing `manual_library.root_dir` layouts remain buildable.
- Existing tests and fixtures should continue to work without requiring S3, MinIO, Docker, network access, or external credentials.
- Sidecar-based KBs remain readable for direct `build_kb(docs_dir, ...)` and eval fixture workflows.

### 2. Manual Registry

- Add a durable registry for managed manuals, initially SQLite.
- Registry records should store at least:
  - `kb_name`
  - `manual_id`
  - `source_file`
  - metadata fields currently represented by `ManualMetadata`
  - `status`
  - `checksum`
  - `content_type`
  - `size_bytes`
  - `blob_key`
  - `storage_backend`
  - `version`
  - `created_at`
  - `updated_at`
  - optional `created_by` / `updated_by` when auth context is available
- Registry should support active, disabled, archived, and hard-deleted lifecycle states.
- Registry should preserve enough state to list manuals without scanning a filesystem.

### 3. Audit Timeline

- Record manual lifecycle events:
  - create/upload
  - metadata update
  - file replace
  - disable
  - archive
  - delete
  - rebuild requested/succeeded/failed when attributable to manual changes
- Audit events should include low-cardinality operation details, timestamps, actor identity when available, checksum/blob changes, and outcome.
- Audit logs must not include raw document content, secrets, full local absolute paths, or large/high-cardinality payloads.

### 4. Pluggable Blob Store

- Introduce a blob-store abstraction for original uploaded file bytes.
- Minimum operations:
  - `put(kb_name, manual_id, source_file, content, metadata) -> BlobRef`
  - `get(blob_key) -> bytes` or stream
  - `delete(blob_key)`
  - `exists(blob_key)`
  - optional `copy` / `open_read` if useful for rebuild staging
- `BlobRef` should include `backend`, `blob_key`, `checksum`, `size_bytes`, and `content_type`.
- Local blob store should be implemented first and remain default.
- S3-compatible backend should be designed in M26 and may be implemented in M27 if scope is too large, but config and interfaces should not block it.

### 5. Rebuild Compatibility

- Managed-library rebuilds should be able to build from registry records plus blob-store content.
- Exact parser behavior should be preserved: source files, metadata, path/header handling, chunk identity, incremental rebuild impact summaries, and Qdrant sync remain compatible.
- A staging strategy is acceptable for MVP: materialize active registry records into a temporary local docs tree before calling the existing parser/build path.
- Failed staging or blob reads must not clear dirty state or swap the active graph.

### 6. API / CLI / Admin UI Compatibility

- Existing upload, replace, metadata update, disable/archive/delete, bulk import, dirty-state, and rebuild APIs remain backward compatible where practical.
- New fields such as `blob_key`, `storage_backend`, `size_bytes`, and `version` may be additive in admin/manual responses.
- CLI commands should expose registry inspection and migration operations if implemented:
  - inspect registry health
  - migrate local sidecars into registry
  - verify blob existence
- Admin UI can remain mostly unchanged for M26 but should display storage backend and registry status if available.

### 7. Migration

- Provide a migration path from current local sidecar layout into the registry.
- Migration must be idempotent.
- Migration should not move/delete existing files by default.
- Operators should be able to dry-run migration and see counts for imported records, skipped records, invalid metadata, missing files, and duplicate manual ids.

### 8. Configuration

- Add configuration under a clear namespace, for example:
  - `manual_library.registry_backend: file | sqlite`
  - `manual_library.registry_path`
  - `manual_library.blob_backend: local | s3`
  - `manual_library.blob_root_dir`
  - `manual_library.s3_bucket`
  - `manual_library.s3_prefix`
  - `manual_library.s3_endpoint_url`
  - `manual_library.s3_region`
  - `manual_library.s3_access_key_env`
  - `manual_library.s3_secret_key_env`
- Do not store raw S3 credentials in YAML.
- Env overrides must follow the existing `TAGMEMORAG__...` settings pattern.

## Acceptance Criteria

- [ ] A Trellis design exists for registry schema, blob-store contract, migration, rebuild staging, API/CLI compatibility, and rollout/rollback.
- [ ] Local disk remains the default and all existing tests continue to pass.
- [ ] Managed manual upload/replace/update/delete can write through the new local blob-store boundary.
- [ ] Managed manual listing can read from the registry when enabled without scanning sidecars.
- [ ] Migration from existing local sidecars to registry is idempotent and covered by tests.
- [ ] Registry/audit operations use atomic or transactional writes.
- [ ] Rebuild from registry-backed managed library preserves chunk metadata and dirty-state safety.
- [ ] API/CLI/admin responses expose only safe storage metadata.
- [ ] No default test requires live S3, MinIO, Qdrant, browser automation, network access, or external model downloads.
- [ ] README documents local default, registry mode, migration, object-storage roadmap, and recovery guidance.

## Definition of Done

- Planning docs are complete before implementation starts.
- Implementation includes focused unit tests for registry, blob store, migration, and rebuild staging.
- Integration/e2e tests cover the existing upload -> rebuild -> search path in local registry mode.
- Full `uv run pytest tests/ -q` passes.
- Documentation explains how to stay on local storage, enable SQLite registry, run migration, and plan S3-compatible storage.

## Out of Scope For M26 MVP

- Making S3 the default backend.
- Requiring MinIO/S3 in default tests.
- Multi-region object replication.
- Presigned browser uploads directly to object storage.
- Database-backed vector storage.
- Replacing Qdrant vector persistence.
- Full role-based audit UI.
- Background rebuild queue and cancellation; this should be a follow-up milestone.

## Research References

- `src/tagmemorag/manual_library.py`
- `src/tagmemorag/manual_bulk_import.py`
- `src/tagmemorag/state.py`
- `src/tagmemorag/api.py`
- `src/tagmemorag/cli.py`
- `tests/unit/test_manual_library.py`
- `.trellis/workspace/suixingchen/roadmap.md`

## Open Questions

- Should M26 implement S3-compatible storage immediately, or should it stop at the stable blob-store interface plus local backend and leave S3/MinIO for M27?
