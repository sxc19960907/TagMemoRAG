# implement.md - M6 Manual Library Management Loop

## Implementation Checklist

### Phase A - Contracts and Config

- [x] Add `ManualLibraryConfig` to `src/tagmemorag/config.py` with conservative defaults.
- [x] Add `src/tagmemorag/manual_library.py` with dataclasses for library records, validation messages, and manifest state.
- [x] Implement safe KB library root resolution and safe relative source path validation.
- [x] Reuse `ManualMetadata.from_dict()`, `normalize_tag()`, and `metadata_sidecar_path()` where possible.
- [x] Add tests for path traversal, unsupported suffixes, metadata normalization, and duplicate `manual_id` detection.

### Phase B - File-Backed Library Operations

- [x] Implement metadata validation without writes.
- [x] Implement source file + sidecar upsert with explicit overwrite behavior.
- [x] Implement metadata-only update.
- [x] Implement soft delete via `status=disabled` or `status=archived`.
- [x] Implement hard delete constrained to the library root.
- [x] Implement `.tagmemorag-library.json` pending-change tracking with atomic writes.
- [x] Add unit tests for create/update/delete/list/manifest behavior.

### Phase C - Build Integration

- [x] Update `build_kb()` to skip documents whose sidecar metadata has inactive status.
- [x] Preserve fallback behavior for files without sidecars.
- [x] Add library-aware rebuild helper that resolves the managed root and calls `AppState.start_rebuild()`.
- [x] Clear the pending marker only after rebuild success.
- [x] Add tests proving failed rebuilds keep the old graph and pending state.

### Phase D - API Endpoints

- [x] Add request/response models in `api.py` or a narrow shared module if needed.
- [x] Add `POST /manuals/validate`.
- [x] Add create/upsert endpoint for document upload plus metadata.
- [x] Add metadata update endpoint.
- [x] Add disable/delete endpoint.
- [x] Add `GET /manual-library` list/detail endpoint while preserving current `GET /manuals`.
- [x] Add `POST /manual-library/rebuild`.
- [x] Enforce KB allowlist and write/admin scopes on every mutation.
- [x] Add API tests for auth, validation, upload, conflict, delete, listing, and rebuild.

### Phase E - CLI and Docs

- [x] Add CLI helpers only for workflows that are awkward through HTTP.
- [x] Update README with managed manual library examples.
- [x] Update `product_manuals/README.md` with sidecar plus upload workflow.
- [x] Update README Roadmap to include M5 and M6.
- [x] Document that manual changes become searchable only after successful rebuild.

### Phase F - Spec and Finish

- [x] Run the full test suite.
- [x] Update backend specs if M6 introduces durable conventions for manual library storage, safe uploads, or API scopes.
- [x] Review docs for compatibility with M5 terminology.
- [x] Commit through Trellis finish flow when implementation is complete.

## Validation

- `uv run pytest tests/unit/test_manual_metadata.py -v`
- `uv run pytest tests/unit/test_api.py tests/unit/test_multi_kb.py -v`
- `uv run pytest tests/ -v`
- Manual smoke test:
  - create a temp manual library root
  - upload a Markdown manual with metadata
  - list it through the library endpoint
  - rebuild the KB
  - confirm `/manuals` and `/search` show the new metadata
  - disable it
  - rebuild again
  - confirm filtered search no longer returns it

## Review Gates

- [x] Existing graph-derived `/manuals` clients are not broken.
- [x] New endpoints cannot write or delete outside the configured library root.
- [x] Manual mutations do not alter the served graph until rebuild success.
- [x] Query cache behavior is correct before and after rebuild.
- [x] Auth scopes and KB allowlists are enforced consistently.
- [x] Logs and metrics avoid raw document text, secrets, filenames as labels, and high-cardinality tags.

## Rollback Points

- If upload multipart handling becomes too broad, ship metadata validation and library listing first, then add upload in a follow-up.
- If inactive-status skip in `build_kb()` risks surprising CLI users, gate it behind a config option and default it to enabled only for managed library rebuilds.
- If hard delete is risky, defer hard delete and ship soft delete only.
