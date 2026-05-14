# implement.md - M30 Import/Export Bundles

## Implementation Checklist

- [x] Read backend specs with `trellis-before-dev` before coding.
- [x] Re-read M26, M27, M28, and M29 archived task docs.
- [x] Inspect current registry/blob/manual-library/CLI tests before editing.
- [x] Add bundle domain module:
  - manifest/record/report dataclasses
  - safe ZIP path validation
  - checksum helpers
  - export/inspect/import entry functions
- [x] Implement file-sidecar export.
- [x] Implement SQLite registry export through `ManualBlobStore`.
- [x] Implement bundle inspection and checksum verification.
- [x] Implement import planning with conflict modes.
- [x] Implement file-sidecar import.
- [x] Implement SQLite registry import through `ManualBlobStore`.
- [x] Mark imported records dirty and preserve old graph serving.
- [x] Add CLI commands for export/inspect/import.
- [x] Decide whether API endpoints are MVP or deferred; if included, add auth and request size safeguards.
- [x] Update README operator docs.
- [x] Add focused unit/CLI tests.
- [x] Run focused tests and full suite.

Implementation note: API endpoints are deferred for M30 MVP. The shipped interface is CLI-first to keep archive upload/download handling bounded and avoid introducing large request bodies before a separate API design pass.

## Suggested Implementation Phases

### Phase A - Bundle Format And Inspection

- Add `manual_bundle.py`.
- Implement:
  - `BundleManifest`
  - `BundleRecord`
  - `BundleInspectReport`
  - `safe_bundle_path()`
  - `sha256_bytes()` / `sha256_filelike()`
  - `write_bundle()` minimal internal helper
  - `inspect_bundle()`
- Cover valid bundle, unsupported schema, unsafe path, missing manifest, duplicate entry, checksum mismatch.

Validation:

```bash
uv run pytest tests/unit/test_manual_bundle.py -q
```

### Phase B - Export

- Implement `export_bundle(kb_name, cfg, output_path, options)`.
- For file-sidecar mode, use `list_records()` and safe source path reads.
- For registry mode, use `create_registry()` and `create_blob_store()`.
- Include audit-safe events in registry mode.
- Include dirty report and rebuild impact when available.
- Do not include deleted records by default.

Validation:

```bash
uv run pytest tests/unit/test_manual_bundle.py tests/unit/test_manual_blob_store.py -q
```

### Phase C - Import Planning

- Implement `plan_bundle_import(bundle_path, target_kb, cfg, conflict_mode)`.
- Compare target records using `list_records()`.
- Detect manual id and source_file conflicts.
- Classify rows as `create`, `overwrite`, `skip`, `unchanged`, or `conflict`.
- Add dry-run CLI output.

Validation:

```bash
uv run pytest tests/unit/test_manual_bundle.py -q
```

### Phase D - Import Writes

- Implement `import_bundle()`.
- File-sidecar target:
  - write source file via safe resolved path and temp replace
  - write sidecar with existing metadata helper where available
  - mark dirty
- SQLite target:
  - write blob first through `create_blob_store(cfg).put()`
  - commit registry row through `SQLiteManualRegistry.upsert()`
  - mark dirty
- Preserve current graph and do not trigger rebuild by default.

Validation:

```bash
uv run pytest tests/unit/test_manual_bundle.py tests/unit/test_manual_library.py tests/unit/test_manual_registry.py -q
```

### Phase E - CLI And Optional API

- Add:

```bash
python -m tagmemorag manual-library bundle export --kb default --output kb.bundle.zip --config config.yaml
python -m tagmemorag manual-library bundle inspect --bundle kb.bundle.zip --config config.yaml
python -m tagmemorag manual-library bundle import --bundle kb.bundle.zip --target-kb restored --conflict-mode fail --dry-run --config config.yaml
```

- If API endpoints are included, add focused auth/KB allowlist tests.
- If API endpoints are deferred, document CLI-first explicitly in README.

Validation:

```bash
uv run pytest tests/unit/test_cli.py tests/unit/test_manual_library_api.py -q
```

### Phase F - Docs And Full Validation

- Update README bundle workflow docs.
- Confirm no raw absolute paths, credentials, signed URLs, raw query text, vectors, or stack traces are emitted.
- Run full tests.

Validation:

```bash
uv run pytest tests/ -q
```

## Focused Tests To Add

- Export file-sidecar KB bundle includes manifest, records, blobs, checksums, and dirty state.
- Export SQLite/local registry KB reads bytes from local blob store and includes audit-safe events.
- Export S3-backed registry can use a fake blob store/client and does not include signed URLs or credentials.
- Inspect valid bundle returns counts and checksum status.
- Inspect rejects unsafe ZIP paths.
- Inspect rejects checksum mismatch.
- Inspect rejects unsupported schema.
- Dry-run import reports manual id and source_file conflicts.
- `conflict_mode=fail` aborts before writes.
- `conflict_mode=skip` imports non-conflicting rows.
- `conflict_mode=overwrite` replaces existing manual content/metadata.
- Import into file-sidecar mode writes source + sidecar and marks dirty.
- Import into SQLite registry mode writes blob + registry row and marks dirty.
- Import failure preserves current graph and does not clear dirty state.
- CLI export/inspect/import produce JSON output.
- API auth/KB allowlist tests if API endpoints are added.

## Review Gates

- Bundle archive entry validation happens before extraction or writes.
- Bundle checksums are verified before import writes.
- Import writes through existing metadata validation and blob-store boundaries.
- Registry import writes blob before registry row.
- Dirty state is marked after imported changes and cleared only by existing successful rebuild path.
- No code path writes outside the target KB library/blob root.
- No bundle metadata includes secrets, signed URLs, absolute paths, vectors, Qdrant dumps, raw queries, or stack traces.
- Existing manual upload, bulk import, registry migration, queue, and diagnostics flows remain compatible.

## Rollback Points

- If registry import proves risky, ship export/inspect plus file-sidecar import first.
- If API upload/download handling is too large for MVP, ship CLI-only and document API as future work.
- If preserving audit events exactly complicates safety, export audit-safe history for inspection but do not import it into target registry in MVP.
- If deleted-record handling is ambiguous, exclude deleted records by default and defer `--apply-deletes`.

## Validation

Focused:

```bash
uv run pytest tests/unit/test_manual_bundle.py -q
uv run pytest tests/unit/test_cli.py -q
uv run pytest tests/unit/test_manual_library.py tests/unit/test_manual_registry.py tests/unit/test_manual_blob_store.py -q
```

Full:

```bash
uv run pytest tests/ -q
```
