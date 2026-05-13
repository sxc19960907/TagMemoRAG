# implement.md - M10 Manual Library Bulk Import and Validation

## Implementation Checklist

- [x] Read current backend specs with `trellis-before-dev` before coding.
- [x] Add `manual_bulk_import.py` with metadata parsers for JSON, JSONL, and CSV.
- [x] Define batch candidate, preview issue, and preview/import result contracts.
- [x] Reuse existing `ManualMetadata` normalization and `manual_library` safe path/file suffix validation.
- [x] Implement uploaded-file-to-metadata matching by `source_file` and filename.
- [x] Implement conflict detection for duplicate `manual_id`, duplicate `source_file`, missing file/metadata pairs, unsupported suffixes, unsafe paths, and existing-library conflicts.
- [x] Add `POST /manual-library/bulk/preview`.
- [x] Add `POST /manual-library/bulk/import`, rerunning preview before writes.
- [x] Ensure import modes support create-only, upsert, dry-run, explicit overwrite, and optional selected rows.
- [x] Mark manual library pending after successful mutating import.
- [x] Add admin UI bulk import controls to the existing M7 template/static JS/CSS.
- [x] Add README and `product_manuals/README.md` documentation with CSV and JSON examples.
- [x] Add tests for parser behavior, preview summaries, conflict rows, commit behavior, auth, and UI route/static behavior.

## Validation

- `uv run pytest tests/unit/test_manual_metadata.py -q`
- `uv run pytest tests/unit/test_manual_library.py tests/unit/test_manual_library_api.py -q`
- `uv run pytest tests/unit/test_manual_library_ui.py -q`
- Add and run new bulk import tests, recommended:
  - `uv run pytest tests/unit/test_manual_bulk_import.py -q`
  - `uv run pytest tests/unit/test_manual_bulk_import_api.py -q`
- Final full check: `uv run pytest tests/ -q`

## Review Gates

- Before coding: confirm whether M10 should use request-local import only or durable staged sessions. Recommended MVP: request-local preview/import with import rerunning preview.
- Before UI work: verify endpoint response shape is stable enough for browser rendering.
- Before finishing: inspect conflict preview UX manually in the browser with at least one valid row, duplicate `manual_id`, duplicate `source_file`, bad tag, unsupported suffix, and existing-library update.

## Rollback Points

- Backend service can ship without UI if API tests pass and docs mark UI as pending.
- UI controls can be hidden without removing single-manual M6/M7 workflows.
- No persisted graph or metadata schema migration is required; rollback does not need KB rebuild.
