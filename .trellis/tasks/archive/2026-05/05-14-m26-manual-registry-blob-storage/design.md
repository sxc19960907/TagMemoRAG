# design.md - M26 Manual Registry and Pluggable File Storage

## Scope

M26 introduces a storage boundary for original uploaded manual files and a durable registry for managed manual metadata. It does not change vector storage, WAVE-RAG ranking, parser behavior, Qdrant candidate generation, or eval fixtures. The design favors a conservative migration: keep local sidecar directories working, add registry/blob-store mode behind config, and stage registry-backed manuals into the existing build path before deeper parser refactors.

## Current Managed-Library Flow

```text
upload file + metadata
  -> manual_library.upsert_manual()
     -> validate metadata
     -> write file under manual_library.root_dir/{kb}/source_file
     -> write source_file.metadata.json sidecar
     -> mark .tagmemorag-library.json dirty

rebuild
  -> state.build_kb(docs_dir=library_root(kb))
     -> scan local files
     -> load sidecar metadata
     -> parse chunks
     -> embed
     -> build graph
     -> save graph/vectors/anchors/chunk identity
     -> clear dirty manifest after successful swap
```

This flow is reliable for local single-node deployments, but it hardcodes uploaded documents to local files and stores lifecycle state in sidecars plus a dirty manifest.

## Target Architecture

```text
API/CLI/admin/manual-bulk
  -> ManualLibraryService
     -> ManualRegistry          (SQLite MVP)
     -> ManualBlobStore         (local MVP; S3-compatible next)
     -> DirtyState/AuditLog
  -> rebuild
     -> RegistryBuildSource
        -> materialize active records to staging docs tree
        -> existing build_kb() parser path
```

The key split:

- **Registry** owns metadata, lifecycle, version, audit, dirty state pointers, and blob references.
- **Blob store** owns original uploaded file bytes.
- **Graph/vector storage** remains unchanged under `storage.data_dir`.

## Proposed Modules

- `src/tagmemorag/manual_registry.py`
  - Dataclasses for `ManualRecord`, `ManualAuditEvent`, `RegistryMigrationReport`.
  - Interface-like base class for registry operations.
  - SQLite implementation.

- `src/tagmemorag/manual_blob_store.py`
  - `BlobRef` dataclass.
  - `ManualBlobStore` protocol/base class.
  - `LocalManualBlobStore` implementation.
  - Optional S3-compatible implementation later.

- `src/tagmemorag/manual_library.py`
  - Keep public functions as compatibility facade.
  - Route to file-sidecar mode or registry mode based on config.
  - Preserve existing return shapes with additive fields.

- `src/tagmemorag/manual_build_source.py` or similar
  - Materialize active registry records to a temporary local tree for rebuild.
  - Write sidecars into staging using existing `ManualMetadata` fields.

## Registry Schema

Initial SQLite tables:

```sql
manual_records(
  kb_name TEXT NOT NULL,
  manual_id TEXT NOT NULL,
  source_file TEXT NOT NULL,
  status TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  checksum TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  blob_backend TEXT NOT NULL,
  blob_key TEXT NOT NULL,
  version INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  created_by TEXT NOT NULL DEFAULT '',
  updated_by TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (kb_name, manual_id)
);

manual_audit_events(
  event_id TEXT PRIMARY KEY,
  kb_name TEXT NOT NULL,
  manual_id TEXT NOT NULL,
  operation TEXT NOT NULL,
  outcome TEXT NOT NULL,
  version INTEGER NOT NULL,
  actor_id TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  detail_json TEXT NOT NULL
);
```

Indexes:

- `(kb_name, source_file)` unique for active/non-deleted records if practical.
- `(kb_name, status)`.
- `(kb_name, manual_id, created_at)` for audit lookup.

Implementation note: SQLite partial unique indexes can enforce active source-file uniqueness, but a simpler MVP can enforce it in transactional code and add tests.

## Blob Key Strategy

Local blob key:

```text
{kb_name}/{manual_id}/{version}/{sha256}-{safe_basename}
```

Rules:

- Do not use absolute local paths as registry blob keys.
- Preserve `source_file` separately because parser metadata and user display depend on it.
- Use content checksum for integrity verification.
- A file replacement writes a new blob/version before updating the registry transaction.

## Local Blob Store Layout

Default local blob root can initially reuse `manual_library.root_dir` for compatibility, but a cleaner registry mode should use:

```text
{manual_library.blob_root_dir}/{kb_name}/{manual_id}/{version}/source.md
```

For migration safety, local registry mode may point blob refs at existing files without moving them, then later compact/copy into blob layout as an optional operation.

## Rebuild Strategy

MVP staging is intentionally conservative:

1. Query registry for active records for `kb_name`.
2. Create a temporary staging directory under `.tmp` or `storage.data_dir/{kb}/staging`.
3. For each record:
   - read blob bytes
   - write them to `staging/{source_file}`
   - write `staging/{source_stem}.metadata.json` from registry metadata
4. Call existing `build_kb(staging_dir, kb_name, cfg, old_state=...)`.
5. On success, save/swap graph exactly as today and clear dirty state.
6. Always remove staging on completion/failure.

Benefits:

- Minimal parser/build churn.
- Existing sidecar metadata loader remains authoritative.
- Existing chunk identity and Qdrant sync paths stay compatible.

Cost:

- Rebuild temporarily writes a local copy of active documents.
- Large KBs may need streaming/staging optimization later.

## API / CLI Compatibility

Existing public shapes should remain valid. Additive fields are acceptable:

- `storage_backend`
- `blob_key` only if it is safe and not an absolute path; otherwise expose `blob_ref_present: true`
- `size_bytes`
- `content_type`
- `version`
- `registry_backend`

CLI additions:

```bash
python -m tagmemorag manual-library registry inspect --kb default
python -m tagmemorag manual-library registry migrate --kb default --dry-run
python -m tagmemorag manual-library registry verify-blobs --kb default
```

Exact CLI shape can be finalized during implementation, but migration and verification should be scriptable.

## Migration Plan

Sidecar-to-registry migration:

```text
scan library_root(kb)
  -> load sidecar metadata
  -> validate source file exists
  -> compute checksum/size/content_type
  -> create registry record if absent
  -> optionally create local blob ref by reference or copy
  -> write audit event
```

Properties:

- Dry-run by default for operator confidence.
- Idempotent: existing matching records are skipped.
- Conflicts reported, not silently overwritten.
- Does not delete sidecars or source files by default.

## Rollout

Recommended rollout phases:

1. Ship code with `manual_library.registry_backend=file` default.
2. Enable `registry_backend=sqlite` in development and migrate one KB.
3. Rebuild from registry-backed staging and compare eval/search behavior.
4. Document fallback: switch back to file mode because original sidecars remain untouched.

## Rollback

- If registry mode fails before graph swap, existing graph continues serving.
- Dirty state must remain pending.
- Operators can switch config back to file mode and rebuild from existing `manual_library.root_dir`.
- Migration does not delete local files, so rollback does not require object-store restore.

## Follow-Up Milestones

- M27: S3-compatible blob store with MinIO test profile and credential-env config.
- M28: Background rebuild queue, cancellation, and retry policy.
- M29: Admin UI history/diagnostics backed by registry and audit events.
- M30: Import/export bundles for registry records plus blobs.
- M31: Production deployment guide covering object storage backups and multi-replica topology.
