# Code Context - M30 Import/Export Bundles

## Existing Storage Boundaries

- `src/tagmemorag/manual_library.py`
  - Public managed-library facade for file-sidecar and registry modes.
  - `list_records(kb_name, cfg, graph_state=None)` returns `ManualLibraryRecord` rows in both modes.
  - `migrate_sidecars_to_registry()` already reads sidecars and writes through blob store + registry.
  - `verify_registry_blobs()` checks registry references through `ManualBlobStore.exists()`.
  - `materialize_registry_build_source()` shows the current registry-to-sidecar staging pattern.
  - Dirty state is controlled by `mark_dirty()`, `mark_pending()`, and `build_dirty_state_report()`.

- `src/tagmemorag/manual_registry.py`
  - `SQLiteManualRegistry` owns registry rows and audit events.
  - `ManualRecord` includes safe blob metadata: backend, key, checksum, content type, size, version.
  - `audit_events(kb_name, manual_id=None)` returns chronological events.
  - Audit detail currently includes safe fields such as source_file, status, checksum, blob_backend, and size_bytes.

- `src/tagmemorag/manual_blob_store.py`
  - `ManualBlobStore` protocol has `put`, `get`, `delete`, and `exists`.
  - `LocalManualBlobStore` and `S3ManualBlobStore` both return `BlobRef`.
  - S3 object keys are safe relative keys; no signed URLs are stored.
  - Existing safe segment/basename/key validation logic should be reused rather than duplicated.

## Existing Entry Points

- `src/tagmemorag/cli.py`
  - `manual-bulk preview/import`
  - `manual-library rebuild`
  - `manual-library rebuild-jobs`
  - `manual-library dirty`
  - `manual-library registry inspect/migrate/verify-blobs`
  - CLI output is JSON-oriented and a natural first surface for bundle workflows.

- `src/tagmemorag/api.py`
  - Manual upload/update/delete/bulk/rebuild endpoints.
  - M29 diagnostics endpoints:
    - `GET /manual-library/diagnostics`
    - `GET /manual-library/registry/audit`
  - API auth patterns use `require_scope()` plus `ensure_kb_access()`.

## Proposed New Module

- `src/tagmemorag/manual_bundle.py`
  - Should own bundle schema, checksum, ZIP path validation, export, inspect, and import domain logic.
  - Should not import FastAPI.
  - May import `manual_library`, `manual_registry`, `manual_blob_store`, config, and errors.
  - CLI/API should orchestrate this module.

## Data Flow To Preserve

Export:

```text
source deployment
  -> registry/list_records
  -> blob_store.get or filesystem read
  -> bundle ZIP with safe manifest + checksums + source bytes
```

Import:

```text
bundle ZIP
  -> validate paths/schema/checksums
  -> plan conflicts against target
  -> write target blob/file
  -> write target registry/sidecar
  -> mark dirty
  -> existing rebuild/queue clears dirty only on success
```

## Main Risks

- ZIP path traversal or accidental extraction outside the target root.
- Importing before checksum/schema validation is complete.
- Leaking S3 endpoint/credentials/signed URLs or local absolute paths in manifest/provenance.
- Treating exported bundles as graph/vector snapshots instead of source-library snapshots.
- Trying to preserve registry versions/audit rows exactly and bypassing existing validation/write paths.
- Partial import writes that are hard to understand; import results need safe cleanup/retry hints.

## Relevant Tests

- `tests/unit/test_manual_library.py`
  - sidecar/registry library behavior and dirty state.
- `tests/unit/test_manual_registry.py`
  - SQLite records and audit behavior.
- `tests/unit/test_manual_blob_store.py`
  - local/S3 blob store safety and fake client patterns.
- `tests/unit/test_cli.py`
  - CLI command JSON output patterns.
- `tests/unit/test_manual_library_api.py`
  - auth/API patterns if bundle endpoints are added.

## Suggested Implementation Shape

- CLI-first MVP.
- Use standard-library `zipfile`.
- Use dataclasses with `to_dict()` for stable JSON payloads.
- Treat deleted records as out of scope by default.
- Mark imports dirty; do not auto-rebuild unless explicitly requested and routed through existing rebuild/queue functions.
- Keep default tests entirely local and deterministic.
