# Code Context - M26 Manual Registry and Pluggable File Storage

Date: 2026-05-14

## Current Upload Storage

- `src/tagmemorag/manual_library.py`
  - `library_root(kb_name, cfg)` returns `manual_library.root_dir/{kb_name}`.
  - `upsert_manual()` validates metadata, writes a source file under `library_root`, writes `*.metadata.json`, then marks dirty state in `.tagmemorag-library.json`.
  - `replace_manual_file()`, `update_manual_metadata()`, `disable_manual()`, and `delete_manual()` all directly manipulate local files/sidecars.
  - `list_records()` scans sidecars to produce admin/manual records.

- `src/tagmemorag/state.py`
  - `build_kb(docs_dir, kb_name, cfg, ...)` scans local files and loads sidecar metadata through `load_manual_metadata()`.
  - Managed-library rebuild resolves `docs_dir = library_root(kb_name, cfg)`.
  - Dirty state clears only after successful graph swap.

- `src/tagmemorag/manual_bulk_import.py`
  - Bulk import validates metadata rows and uploaded files, then commits through manual-library functions.

- `src/tagmemorag/api.py` and `src/tagmemorag/web/static/manual_library.js`
  - Admin upload submits `file`, `metadata`, `overwrite`, and `trigger_rebuild` to `/manuals`.
  - UI wording currently assumes local source/metadata files when deleting.

## Design Implications

- A registry can be introduced behind the existing `manual_library` facade to reduce API/CLI churn.
- Direct `build_kb(docs_dir)` should keep sidecar behavior for fixtures, eval, and existing deployments.
- Registry-backed rebuild can stage files into a temporary sidecar tree to preserve parser/chunk identity behavior.
- Local file mode must remain the default until migration and registry-backed rebuild are proven.

## Likely Files For Implementation

- `src/tagmemorag/config.py`
- `src/tagmemorag/manual_blob_store.py` (new)
- `src/tagmemorag/manual_registry.py` (new)
- `src/tagmemorag/manual_library.py`
- `src/tagmemorag/state.py`
- `src/tagmemorag/api.py`
- `src/tagmemorag/cli.py`
- `src/tagmemorag/manual_bulk_import.py`
- `tests/unit/test_manual_registry.py` (new)
- `tests/unit/test_manual_blob_store.py` (new)
- existing manual-library, API, CLI, bulk-import, and rebuild tests

## Constraints

- No live S3/MinIO dependency in default tests.
- No raw document bodies in registry/audit logs.
- No raw credentials in YAML, logs, metrics, or traces.
- Existing sidecar fixture/eval workflows must remain valid.
