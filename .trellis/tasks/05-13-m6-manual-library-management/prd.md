# M6 Manual Library Management Loop

## Goal

Close the manual management loop around M5 metadata-aware retrieval. M6 turns the current file-plus-sidecar workflow into an API-manageable manual library: authenticated clients can validate manual metadata, upload or update manuals, list and inspect managed manuals, disable or delete manuals, and trigger a safe rebuild so the search graph reflects the library state without breaking the existing WAVE-RAG contracts.

## Background / Known Context

- M0-M4 delivered WAVE-RAG search, anchors, JSON+NPZ storage, FastAPI/CLI, zero-downtime rebuild, operations basics, auth/rate limiting/cache, eval, metrics, and tracing.
- M5 added `ManualMetadata`, sidecar `.metadata.json` loading, fallback metadata, graph node metadata, `/manuals`, search filters, tag-aware boosts, and metadata-aware eval matching.
- Current manual ingestion is filesystem-driven: `build_kb(docs_dir, kb_name, cfg)` scans `.md/.txt/.pdf` files and loads sidecar metadata next to each source file.
- Current `/manuals` is read-only and derives its view from the loaded graph, so it cannot show uploaded-but-not-built files, disabled manuals, validation failures, or pending rebuild state.
- Current `/rebuild` accepts an arbitrary `docs_dir`; M6 should provide a safer library-root workflow while preserving the existing endpoint for compatibility.
- Auth already supports scopes such as `search`, `rebuild`, `anchor.write`, and `admin`. M6 should add or reuse admin-style scopes without bypassing KB allowlists.

## Assumptions

- M6 remains file-backed. A database-backed registry is a follow-up, not part of this task.
- Managed manual source files live under a configured or derived library directory per KB, likely `product_manuals/{kb_name}/` or `storage.data_dir/{kb_name}/manuals/`. The exact path is finalized in design.
- M6 supports text-based PDF, Markdown, and plain text uploads only, matching the existing parser. OCR remains out of scope.
- Manual metadata remains the source of product/category/model/language/tag truth. M6 validates and writes metadata, but does not auto-generate tags with an LLM.
- Rebuild remains asynchronous and double-buffered: failed rebuilds must preserve the currently served graph.

## Requirements

### 1. Managed Manual Library Contract

- Define a file-backed manual library abstraction that owns:
  - source document path
  - sidecar metadata path
  - current metadata
  - lifecycle status such as `active`, `disabled`, or `archived`
  - optional validation errors or warnings
  - last modified timestamp and checksum when cheap
- Keep M5 sidecar metadata compatible. Existing sidecars should continue to build without migration.
- Prevent path traversal and writes outside the configured library root.
- Reject unsupported document suffixes with a structured `INVALID_INPUT` error.

### 2. Metadata Validation API

- Add an endpoint that validates a proposed `ManualMetadata` payload without writing source files.
- Validate all M5 rules:
  - required fields are present
  - `manual_id` is non-empty
  - `source_file` is relative and safe
  - tags normalize to the documented lower-kebab convention
  - duplicate `manual_id` in the target KB is rejected or returned as a conflict depending on operation mode
- Response should include normalized metadata and validation messages so an upload UI can show actionable feedback.

### 3. Upload / Upsert API

- Add an authenticated endpoint to upload or upsert one manual document plus metadata for a target `kb_name`.
- Store the document and matching sidecar atomically enough that rebuild never sees a source file without valid metadata.
- Support explicit overwrite semantics. A create request should not silently replace an existing `manual_id` or source path.
- Return manual library state plus whether a rebuild is required.
- Do not automatically trigger rebuild by default unless the request explicitly asks for it.

### 4. Manual Update API

- Support updating metadata for an existing manual without re-uploading the document.
- Support replacing the source document for an existing manual while keeping or updating metadata.
- Ensure metadata changes invalidate search cache after the rebuild that makes them visible.
- Preserve anchors by relying on existing anchor reconciliation; document that large content changes can leave anchors unresolved.

### 5. Disable / Delete API

- Support disabling a manual so future rebuilds exclude it from search while preserving source and metadata for audit/recovery.
- Support hard delete only for admin users and only inside the library root.
- Deleting or disabling a manual must mark the KB as needing rebuild and must not mutate the currently served graph until rebuild completes.

### 6. Library Listing and Detail API

- Extend or add endpoints to list manuals from the managed library, not only from the loaded graph.
- Include per-manual fields:
  - `manual_id`, title, source file, category/model/language/tags
  - lifecycle status
  - built/searchable status when known
  - chunk count from the loaded graph when available
  - validation state
  - rebuild-required indicator
- Preserve the existing `/manuals` response shape for search-facing clients or version it carefully if extending it.

### 7. Rebuild Integration

- Add a library-aware rebuild path that rebuilds a KB from its managed manual library root.
- Keep the existing `/rebuild {docs_dir,kb_name}` endpoint working.
- A successful library rebuild should clear the "pending changes" marker for that KB.
- A failed rebuild should keep pending changes visible and preserve the old `GraphState`.

### 8. Auth, Audit, and Observability

- Require KB access for every manual-library operation.
- Require a write/admin scope for create/update/disable/delete and a read/search scope for list/detail.
- Log manual library mutations with safe identifiers: `kb_name`, `manual_id`, action, status, and trace id. Do not log raw document text or API secrets.
- Add low-cardinality metrics if useful, but do not add labels for raw `manual_id`, filenames, tags, or query text.

### 9. CLI and Documentation

- Add CLI helpers only if they materially reduce operational friction:
  - validate metadata
  - import/upsert a manual
  - list managed manuals
  - rebuild from library root
- Update README and `product_manuals/README.md` with the managed-library workflow.
- Update the Roadmap to include M5 and M6 so docs match current project state.

## Acceptance Criteria

- [ ] A managed manual can be uploaded/upserted through an authenticated API and persisted as a source file plus compatible metadata sidecar.
- [ ] Metadata validation returns normalized metadata and actionable structured errors without writing files.
- [ ] Manual listing can show managed manuals even before they are rebuilt into the graph.
- [ ] Disabling a manual excludes it from the next library rebuild without deleting the source file.
- [ ] Hard delete is constrained to the library root and cannot path-traverse outside it.
- [ ] Library-aware rebuild is asynchronous, double-buffered, and clears pending-change state only after success.
- [ ] Existing `/search`, `/manuals`, `/rebuild`, anchors, cache, and M5 metadata behavior remain backward compatible.
- [ ] Auth scopes and KB allowlists are enforced for every new endpoint.
- [ ] Unit and API tests cover validation, upload/upsert, conflict behavior, disable/delete safety, listing, and rebuild integration.
- [ ] README and product manual docs describe the managed workflow.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- Tests are added or updated for all new API/library behaviors.
- `uv run pytest tests/ -v` passes.
- Any new reusable storage, auth, or logging conventions are added to `.trellis/spec/backend/` if they should guide future work.
- The old graph continues serving during failed library rebuilds.

## Out of Scope

- Browser UI for manual management.
- Database-backed manual registry.
- Object storage/S3.
- OCR for scanned PDFs.
- Automatic tag generation by LLM.
- Cross-KB federated retrieval.
- Full RBAC beyond the existing scope plus KB allowlist model.
- Multi-replica rebuild coordination.

## Follow-Up Ideas

- Browser UI for upload, metadata editing, and rebuild status.
- SQLite/PostgreSQL registry with audit history.
- OCR pipeline and text-extraction status.
- Tag suggestions from filename/content.
- Query classifier that routes likely category/model automatically.
- Scheduled library rebuilds and drift detection.
