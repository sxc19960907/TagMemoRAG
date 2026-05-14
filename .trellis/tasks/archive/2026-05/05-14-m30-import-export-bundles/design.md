# design.md - M30 Import/Export Bundles

## Scope

M30 adds a portable bundle layer for managed manual libraries. It should not change parser behavior, WAVE ranking, graph/vector persistence, Qdrant sync semantics, S3 object-key generation, rebuild execution, or admin UI layout unless needed for small links to bundle workflows.

Primary work:

- Define a safe bundle archive format.
- Add service helpers to export, inspect, verify, and import bundles.
- Add CLI commands for export/inspect/import.
- Optionally add bounded API endpoints after CLI behavior is stable.
- Mark imported changes dirty and rely on existing rebuild/queue paths.

## Current State

```text
file-sidecar mode:
  manual_library.root_dir/{kb}/source files
  source.metadata.json sidecars
  .tagmemorag-library.json dirty manifest

registry mode:
  SQLiteManualRegistry records + audit events
  ManualBlobStore local|s3 for original bytes
  materialize_registry_build_source() stages active records for rebuild

diagnostics:
  registry_inspect()
  verify_registry_blobs()
  build_dirty_state_report()
  /manual-library/diagnostics
```

The missing piece is a portable representation that can be created from either mode and imported into either mode without exposing deployment-specific storage details.

## Target Architecture

```text
CLI/API
  -> manual_bundle.py
       export_bundle(kb, output, cfg, options)
         -> list source records from registry or sidecars
         -> read source bytes through ManualBlobStore or filesystem
         -> write ZIP with manifest, records, blobs, state, checksums

       inspect_bundle(bundle, cfg?, target_kb?, options)
         -> validate ZIP entry names
         -> load manifest and records
         -> verify checksums
         -> optionally compare target conflicts

       import_bundle(bundle, target_kb, cfg, options)
         -> inspect and validate
         -> dry-run conflict plan
         -> write blobs through target backend
         -> write registry rows or sidecars
         -> mark dirty
```

Proposed module:

- `src/tagmemorag/manual_bundle.py`
  - dataclasses for manifest, record entries, inspect report, import plan, import result
  - ZIP read/write helpers
  - checksum helpers
  - safe path validation
  - mode-specific adapters for file-sidecar and registry-backed libraries

Entry points:

- `src/tagmemorag/cli.py`
  - `manual-library bundle export`
  - `manual-library bundle inspect`
  - `manual-library bundle import`

- `src/tagmemorag/api.py` optional
  - expose bounded endpoints only if request body/file handling remains simple and tested

## Bundle Layout

Use ZIP so default tests and local operators do not need new dependencies.

```text
tagmemorag-bundle.json
checksums.json
records/
  cm1.json
  cm2.json
blobs/
  cm1/1/9f86d081884c7d65-cm1.md
  cm2/3/f3a1...-cm2.pdf
audit/
  events.jsonl
state/
  dirty.json
  rebuild_impact.json
```

Rules:

- All paths are UTF-8 safe relative paths using `/`.
- Reject empty names, absolute paths, `.`/`..` segments, duplicate names, and unsupported top-level directories.
- JSON files use sorted keys and UTF-8.
- Blob file names reuse safe basename and checksum prefix patterns from `manual_blob_store.py`.
- Bundle export should produce stable ordering for records, audit events, checksum rows, and ZIP entries where practical.

## Manifest Contract

`tagmemorag-bundle.json`:

```json
{
  "schema_version": 1,
  "bundle_id": "uuid",
  "created_at": "2026-05-14T...",
  "kb_name": "default",
  "source": {
    "registry_backend": "sqlite",
    "blob_backend": "s3",
    "tagmemorag_version": ""
  },
  "counts": {
    "manual_count": 2,
    "blob_count": 2,
    "audit_event_count": 8,
    "dirty_manual_count": 1
  },
  "records": [
    {
      "manual_id": "cm1",
      "record_path": "records/cm1.json",
      "blob_path": "blobs/cm1/1/9f86d081884c7d65-cm1.md",
      "checksum": "sha256..."
    }
  ]
}
```

Do not include absolute paths, bucket names unless already in safe diagnostics, endpoints, credentials, signed URLs, or raw stack traces.

## Record Contract

Each `records/{manual_id}.json`:

```json
{
  "schema_version": 1,
  "kb_name": "default",
  "manual_id": "cm1",
  "source_file": "coffee/cm1.md",
  "metadata": {
    "manual_id": "cm1",
    "title": "CM1 Manual",
    "source_file": "coffee/cm1.md",
    "product_category": "coffee",
    "language": "zh-CN",
    "tags": ["maintenance"],
    "status": "active"
  },
  "status": "active",
  "version": 3,
  "checksum": "sha256...",
  "content_type": "text/markdown",
  "size_bytes": 1234,
  "blob": {
    "path": "blobs/cm1/3/...",
    "source_backend": "s3",
    "source_blob_key": "safe/object/key"
  },
  "created_at": "2026-05-14T...",
  "updated_at": "2026-05-14T..."
}
```

`source_blob_key` is optional and safe only: object key or local blob key, never full URL or absolute path. The import path should not depend on it; it is diagnostic provenance.

## Checksum Contract

`checksums.json` maps bundle-relative paths to SHA-256:

```json
{
  "algorithm": "sha256",
  "entries": {
    "tagmemorag-bundle.json": "...",
    "records/cm1.json": "...",
    "blobs/cm1/3/...": "..."
  }
}
```

To avoid self-reference, either exclude `checksums.json` from its own entries or include a `checksums_payload_sha256` in the manifest. Prefer excluding `checksums.json` and documenting that rule.

## Export Flow

### Registry Mode

```text
registry.list(kb, include_deleted? false by default)
  -> for each record:
       blob_store.get(record.blob_key)
       verify checksum matches record.checksum
       write record JSON
       write blob payload
  -> registry.audit_events(kb)
  -> build_dirty_state_report(kb)
  -> optional rebuild_impact.json copy
```

Deleted records should be excluded by default because their blob may be gone. Add `--include-deleted` only if implementation can represent missing blobs safely.

### File-Sidecar Mode

```text
list_records(kb, cfg, graph_state=None)
  -> read source bytes from library root/source_file
  -> write record JSON from sidecar-derived ManualLibraryRecord
  -> no registry audit events
  -> include dirty manifest and rebuild impact if present
```

File-sidecar export should not copy arbitrary files from the KB directory. Only source files with valid metadata/listing records are included.

## Inspect Flow

`inspect_bundle(path, target_kb=None, cfg=None)`:

1. Open ZIP and validate every entry path.
2. Load manifest.
3. Validate schema version.
4. Load records and verify required fields.
5. Verify checksums for JSON and blob entries.
6. Optionally compare records to target KB:
   - existing manual id
   - existing source_file conflict
   - checksum same/different
   - status conflict
7. Return JSON report with counts, warnings, errors, and conflict rows.

Inspection must not write to the target deployment.

## Import Flow

Options:

- `target_kb`: default to manifest `kb_name`
- `conflict_mode`: `fail | skip | overwrite`
- `dry_run`: default false for CLI import, true for inspect
- `trigger_rebuild`: default false
- `restore_dirty_state`: default false or `merge`; MVP can simply mark imported records dirty

Algorithm:

```text
inspect bundle
build import plan
if dry_run: return plan

for each planned record:
  read blob bytes
  validate metadata and source_file with existing manual_library validators
  if registry mode:
    blob_ref = create_blob_store(cfg).put(target_kb, manual_id, source_file, bytes, {"version": next_version})
    registry.upsert(target_kb, metadata, blob_ref, operation="bundle_import")
  else:
    write source file through safe_source_path + temp replace
    write sidecar metadata atomically
  mark_dirty(target_kb, manual_id, source_file, operation="bundle_import", checksum=checksum)

if trigger_rebuild:
  call existing immediate/queued rebuild request path from CLI/API layer
```

Implementation detail: there is no current public `upsert_manual()` variant that preserves imported version/audit timestamps. MVP can import as a new upload/update operation and store original bundle provenance in safe audit detail or result reports rather than trying to preserve registry primary keys exactly.

## Conflict Semantics

- `fail`: any existing manual id or source_file conflict aborts before writes.
- `skip`: skip conflicting rows; import non-conflicting rows.
- `overwrite`: replace existing manual metadata/file through existing write paths.
- Same checksum and same normalized metadata may be treated as `unchanged` and skipped with an info row.
- Deleted source records from bundles are not applied as destructive deletes in MVP unless a future explicit `--apply-deletes` admin-only option is designed.

## Error Matrix

- Missing manifest -> `INVALID_INPUT`
- Unsupported schema -> `STORAGE_SCHEMA_MISMATCH` or `INVALID_INPUT`
- Unsafe ZIP path -> `INVALID_INPUT`
- Duplicate ZIP path -> `INVALID_INPUT`
- Missing checksum entry -> `INVALID_INPUT`
- Checksum mismatch -> `STORAGE_LOAD_FAILED`
- Missing blob entry -> `STORAGE_LOAD_FAILED`
- Malformed record metadata -> `INVALID_INPUT`
- Target conflict under `fail` -> `INVALID_REQUEST`
- S3/local blob write failure -> existing `ManualBlobStore` service errors
- Registry transaction failure -> `STORAGE_LOAD_FAILED` or existing registry error mapping

All error details must use safe fields such as `bundle_path`, `manual_id`, `source_file`, `expected_checksum`, `actual_checksum`, and `conflict_mode`.

## Auth And API Notes

CLI does not need auth. If API endpoints are added:

- Export requires `require_scope("rebuild")` and KB access.
- Inspect requires `require_scope("rebuild")` if comparing with target KB; pure bundle inspection can still require rebuild for simplicity.
- Import with `conflict_mode=fail|skip` requires `rebuild`; `overwrite` and any future delete application require `admin`.
- Avoid long synchronous export/import over HTTP for large bundles unless request size limits and temp-file cleanup are explicit.

## Testing Strategy

Default tests stay offline:

- Unit tests for safe ZIP path validation.
- Unit tests for manifest/checksum read-write round trip.
- File-sidecar export -> inspect -> import into empty file-sidecar KB.
- SQLite/local blob export -> inspect -> import into empty SQLite/local blob KB.
- Registry export with a fake S3 blob store or local S3 fake if existing test helpers support it.
- Conflict modes: fail, skip, overwrite, unchanged.
- Corruption cases: checksum mismatch, missing blob, malformed metadata, unsupported schema, path traversal.
- CLI JSON output tests for export/inspect/import dry-run.
- Rebuild safety: import marks dirty and does not swap active graph.

## Rollout And Rollback

- Ship CLI-first with no config changes required.
- Keep bundle import explicit; no automatic import on startup.
- Roll back by deleting imported target records/files using existing manual APIs or restoring from backup; dirty state remains visible until rebuild.
- If import writes blobs but fails before registry commit, report safe cleanup candidates and allow rerun with overwrite/skip.
- Do not mutate source deployment during export.
