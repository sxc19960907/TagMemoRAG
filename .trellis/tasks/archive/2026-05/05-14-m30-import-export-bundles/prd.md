# M30 Import/Export Bundles

## Goal

Add portable managed-library bundles so operators can export a KB's manual registry, source blobs, dirty/build diagnostics, and safe manifest metadata from one TagMemoRAG deployment, then import that bundle into another local or object-storage-backed deployment.

M30 should make disaster recovery, environment migration, and offline handoff practical without copying raw SQLite files, object-store buckets, Qdrant collections, or machine-specific directory trees by hand.

## Background / Known Context

- M26 added SQLite manual registry records, lifecycle audit events, local blob refs, sidecar migration, and registry-backed rebuild staging.
- M27 added S3-compatible blob storage behind `ManualBlobStore`; registry rows store safe object keys, not signed URLs or credentials.
- M28 added an opt-in in-process rebuild queue. Dirty state remains the source of truth for pending manual changes.
- M29 added admin diagnostics for registry status, blob verification, audit timeline, queue jobs, dirty state, and recovery guidance.
- Current backup/migration guidance is still manual: copy sidecar files, SQLite registry, blob directories, and object-store data separately, then inspect dirty/rebuild state.

## Problem

Production and staging operators need repeatable ways to move or restore managed manuals:

- A registry-backed KB cannot be moved safely by copying only `manual_library.root_dir`.
- S3-backed source blobs may live outside the application filesystem, so local backup scripts miss them.
- Copying raw SQLite registry files between deployments can carry machine-specific paths and operational state that should not be blindly imported.
- Operators need to verify bundle integrity before import and understand whether the target KB will require rebuild.
- Disaster recovery should restore original manual bytes and metadata before rebuilding graph/vector/Qdrant artifacts.

## Requirements

### 1. Bundle Export

- Add a scriptable export flow for a single `kb_name`.
- Export should include:
  - bundle manifest with schema version, bundle id, created_at, kb_name, source TagMemoRAG version if available, registry/blob backend summaries, and counts
  - manual records with metadata, lifecycle status, checksum, content type, size, version, source_file, blob_backend, and safe logical blob ids
  - original manual source bytes for active, disabled, and archived manuals unless explicitly filtered
  - audit-safe event summaries when registry mode is enabled
  - dirty-state snapshot and latest rebuild impact/Qdrant summaries when available
  - checksum index for every bundled file
- Export must not include:
  - raw credentials, signed URLs, request headers, stack traces, API tokens, environment values, absolute local paths, vectors, raw graph internals, Qdrant collection dumps, or search query text
  - arbitrary unbounded audit detail beyond the existing safe audit fields
- Export should work in both file-sidecar mode and SQLite registry mode.
- Export from S3-backed registry mode should fetch bytes through `ManualBlobStore.get()` and store them inside the bundle, not store external S3 URLs.

### 2. Bundle Format

- Use a deterministic, portable archive format based on standard tooling, preferably ZIP through Python's standard library.
- The bundle should be self-describing and inspectable without importing.
- Bundle paths must be normalized safe relative paths.
- Recommended logical layout:

  ```text
  tagmemorag-bundle.json
  checksums.json
  records/<manual_id>.json
  blobs/<manual_id>/<version>/<safe_basename>
  audit/events.jsonl
  state/dirty.json
  state/rebuild_impact.json
  ```

- Bundle schema must have an explicit version and compatible import policy.
- Checksums should cover raw blob bytes and JSON metadata files.

### 3. Bundle Import

- Add a scriptable import flow into a target `kb_name`.
- Import should support:
  - dry-run validation with counts and conflicts
  - conflict modes such as `fail`, `skip`, and `overwrite`
  - optional source KB name remapping
  - writing original bytes through the target deployment's configured `ManualBlobStore`
  - committing registry rows when `manual_library.registry_backend=sqlite`
  - restoring sidecar files when target registry mode is `file`
- Import must be transactional where practical:
  - validate manifest and checksums before mutating
  - write blobs before registry rows
  - avoid partial registry updates on validation failure
  - report any partial blob writes with safe cleanup/retry guidance
- Import should mark the target KB pending rebuild and dirty for imported or changed manuals.
- Import should not automatically rebuild unless an explicit flag is added and accepted through existing rebuild/queue behavior.

### 4. Verification And Inspection

- Add commands/API support to inspect a bundle before import:
  - schema version
  - source KB
  - manual counts by status
  - blob count and total size
  - checksum verification result
  - audit event count
  - whether import would conflict with target records
- Verification output must be JSON-friendly and safe for logs.
- Corrupted checksum, missing manifest, unsafe archive path, unsupported schema, missing blob, and malformed metadata must fail with structured errors.

### 5. API And CLI Contracts

- CLI should be the primary M30 interface:
  - `manual-library bundle export`
  - `manual-library bundle inspect`
  - `manual-library bundle import`
- Add API endpoints only if the implementation can keep request/response handling bounded and safe:
  - `POST /manual-library/bundles/export`
  - `POST /manual-library/bundles/import`
  - `POST /manual-library/bundles/inspect`
- Export and import require `rebuild` scope plus KB allowlist access. Overwriting existing target manuals or importing deleted records should require `admin` if exposed over API.
- Existing manual upload, bulk import, registry migration, rebuild, queue, and diagnostics endpoints must remain backward compatible.

### 6. Safety And Security

- Validate all archive entry names against path traversal and absolute path attacks.
- Never trust bundle metadata until checksums and schema validation pass.
- Do not extract archives directly into the final library root.
- Do not import arbitrary files outside the documented bundle layout.
- Do not include raw document text in diagnostics, logs, audit event details, metrics, traces, or error messages; raw source bytes may exist only inside the bundle's blob payload.
- Keep bundle imports deterministic and idempotent under the selected conflict mode.

### 7. Rebuild And Queue Integration

- Import must leave the old graph serving until a later successful managed-library rebuild.
- Import must mark dirty state so M21/M29 diagnostics show the KB needs rebuild.
- If queueing is enabled and the user requests rebuild after import, reuse existing queue behavior instead of adding a bundle-specific worker.
- Import failure must not clear dirty state or alter the current graph/vector/Qdrant artifacts.

### 8. Documentation

- README should document:
  - bundle export/inspect/import examples
  - file-sidecar versus registry-backed behavior
  - S3-backed export behavior
  - conflict modes and dry-run flow
  - disaster recovery sequence
  - migration between local and object-storage-backed deployments
  - rollback if import validation or rebuild fails

## Acceptance Criteria

- [ ] PRD/design/implementation plan exist before implementation starts.
- [ ] Bundle format has explicit schema version, safe relative paths, manifest, checksums, records, blobs, audit-safe events, and dirty/rebuild state snapshots.
- [ ] CLI can export a file-sidecar KB into a portable bundle.
- [ ] CLI can export a SQLite registry KB with local or S3 blobs by reading through `ManualBlobStore`.
- [ ] CLI can inspect and checksum-verify a bundle without importing it.
- [ ] CLI can dry-run import and report conflicts without writing.
- [ ] CLI can import into file-sidecar mode and SQLite registry mode.
- [ ] Imported manuals are marked dirty and require rebuild; the old graph remains serving until rebuild succeeds.
- [ ] Conflict handling covers fail, skip, and overwrite.
- [ ] Unsafe bundle paths, unsupported schema, malformed metadata, missing blobs, and checksum mismatches return structured safe errors.
- [ ] API endpoints, if added, enforce rebuild/admin scope and KB allowlist patterns.
- [ ] Tests use local temporary files and fake blob stores; default tests require no S3, MinIO, Qdrant, network, or external credentials.
- [ ] README documents bundle workflows and recovery guidance.
- [ ] `uv run pytest tests/ -q` passes.

## Definition Of Done

- M30 documentation is complete and checked into `.trellis/tasks/`.
- Implementation uses existing `ManualBlobStore`, `SQLiteManualRegistry`, sidecar metadata, dirty manifest, rebuild queue, and structured error patterns.
- No raw secrets, signed URLs, stack traces, vectors, absolute paths, or query text are emitted in bundle metadata or diagnostics.
- Bundle import/export is covered by focused unit tests and CLI tests.
- Full test suite passes.

## Out Of Scope For M30 MVP

- Exporting graph/vector/Qdrant artifacts as authoritative serving state.
- Direct object-store-to-object-store copy without local bundle materialization.
- Streaming multi-gigabyte bundle upload/download API.
- Bundle encryption, signing, KMS, or key rotation.
- Cross-version migration beyond one explicit schema compatibility window.
- Multi-KB bundles.
- Durable external queueing or multi-replica coordination.
- Production deployment runbooks; M31 owns deployment docs.

## Research References

- `.trellis/workspace/suixingchen/roadmap.md`
- `.trellis/tasks/archive/2026-05/05-14-m26-manual-registry-blob-storage/`
- `.trellis/tasks/archive/2026-05/05-14-m27-s3-compatible-blob-store/`
- `.trellis/tasks/archive/2026-05/05-14-m28-background-rebuild-queue-cancellation/`
- `.trellis/tasks/archive/2026-05/05-14-m29-admin-ui-history-diagnostics/`
- `src/tagmemorag/manual_library.py`
- `src/tagmemorag/manual_registry.py`
- `src/tagmemorag/manual_blob_store.py`
- `src/tagmemorag/manual_bulk_import.py`
- `src/tagmemorag/cli.py`
- `src/tagmemorag/api.py`
- `tests/unit/test_manual_library.py`
- `tests/unit/test_manual_registry.py`
- `tests/unit/test_manual_blob_store.py`
- `tests/unit/test_cli.py`
