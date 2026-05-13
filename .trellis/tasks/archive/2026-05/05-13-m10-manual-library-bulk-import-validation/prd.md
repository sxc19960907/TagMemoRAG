# M10 Manual Library Bulk Import and Validation

## Goal

Make Manual Library practical for operations teams that need to onboard many manuals at once. M10 adds batch document upload, batch metadata JSON/CSV import, batch validation, and an upload-before-write conflict preview showing `manual_id`, `source_file`, `tag`, and `status`, so operators can catch duplicate IDs, unsafe paths, bad tags, unsupported files, and overwrite risk before changing the managed library.

## Background / Known Context

- M5 introduced `ManualMetadata`, sidecar `.metadata.json` loading, metadata filters, and tag-aware retrieval.
- M6 introduced the file-backed managed manual library API and library-aware rebuild flow.
- M7 introduced `/admin/manual-library`, a lightweight operations UI on top of the M6 JSON APIs.
- M8 added deterministic tag suggestions in the admin UI, but `POST /manuals/validate` remains the canonical normalization and validation check.
- Current upload and validation flows are single-manual oriented. This is painful when an operator receives a directory of product PDFs plus a spreadsheet of metadata.
- Manual library changes should remain non-searchable until a successful library rebuild; M10 must preserve that serving contract.

## Assumptions

- M10 remains file-backed and builds on the M6 library root. A DB registry and audit timeline remain follow-ups.
- Batch uploads support `.md`, `.txt`, and text-based `.pdf`, matching existing parser support.
- Metadata can arrive as JSON, JSONL, or CSV. CSV is important for operations users because spreadsheets are the likely editing surface.
- Batch import should default to preview/validate first. Mutating writes require an explicit commit/import call.
- Conflict preview should be available through API and UI; CLI support is useful if it stays thin over the same backend service.
- Tag suggestion may assist metadata drafting, but M10 does not auto-accept suggested tags during import.

## Requirements

### 1. Batch Import Session Contract

- Add a batch import concept that can stage or analyze many candidate manuals for one `kb_name`.
- Each candidate must have:
  - `manual_id`
  - `source_file`
  - source document reference or upload file name
  - metadata fields supported by `ManualMetadata`
  - normalized `tags`
  - candidate `status`
- The API must support previewing a batch without writing source files or sidecars.
- The mutation step must be explicit and must only write records that passed validation or were explicitly selected according to a documented policy.

### 2. Batch Document Upload

- Support uploading multiple documents in one request or import session.
- Match uploaded files to metadata by `source_file`, filename, or an explicit manifest mapping.
- Reject unsupported suffixes with structured per-row errors.
- Enforce the same safe-path constraints as M6 for every candidate.
- Do not allow one invalid file to partially corrupt already existing library files.

### 3. Batch Metadata JSON/CSV Import

- Accept metadata as:
  - JSON array
  - JSONL
  - CSV with documented column names
- Required columns/fields must align with `ManualMetadata`: `manual_id`, `title`, `source_file`, `product_category`, `language`.
- Optional columns should include `brand`, `product_name`, `product_model`, `version`, `tags`, `notes`, and `status`.
- CSV tag parsing must be documented and deterministic, recommended comma or newline separated values.
- Unknown columns should be preserved only if they are already accepted by the metadata model; otherwise report warnings or errors consistently.

### 4. Batch Validate

- Validate all candidates with the same rules as single-manual validation.
- Detect intra-batch conflicts:
  - duplicate `manual_id`
  - duplicate `source_file`
  - metadata source path not matched by an uploaded document
  - uploaded document without metadata
  - conflicting `status` values for the same target
- Detect conflicts against the existing manual library:
  - existing `manual_id`
  - existing `source_file`
  - disabled/archived target being reintroduced
  - overwrite requiring explicit approval
- Return per-row validation results and an aggregate summary.

### 5. Upload-Before-Write Conflict Preview

- Provide a preview table shaped for UI display with at least:
  - `row`
  - `manual_id`
  - `source_file`
  - `tag`
  - `status`
  - `action`
  - `severity`
  - `message`
- The preview must distinguish:
  - `create`
  - `update`
  - `skip`
  - `conflict`
  - `invalid`
- The UI-facing summary should group by `manual_id`, `source_file`, `tag`, and `status`, because those are the fastest operational fields to scan.

### 6. Batch Commit / Import

- Provide a commit endpoint that applies a validated batch.
- Support explicit operation modes:
  - create-only: reject existing `manual_id` or `source_file`
  - upsert: update existing records only when explicitly allowed
  - dry-run: validate and preview only
- Writes should be as atomic as practical per candidate and safe at the library level:
  - write source and sidecar together
  - leave existing files untouched on failed validation
  - return a clear partial-failure report if a filesystem write fails mid-batch
- A successful mutating batch marks the KB library as pending rebuild.
- Do not trigger rebuild by default. Optional trigger rebuild may be supported, default off.

### 7. Admin UI Integration

- Extend `/admin/manual-library` with a bulk import workflow.
- The workflow should include:
  - multi-file picker
  - metadata JSON/CSV upload or paste/import area
  - preview/validate action
  - conflict table with filters by severity/action/status/tag
  - selectable rows or all-valid import
  - explicit overwrite/upsert controls
- Keep the UI operations-console style from M7: dense, scannable, and conservative around destructive changes.
- Show pending rebuild state after a successful import.

### 8. CLI and Documentation

- Add CLI helpers if they stay thin over the same backend/library behavior:
  - batch validate metadata
  - preview import conflicts
  - commit an import
- Update README and `product_manuals/README.md` with:
  - CSV template
  - JSON/JSONL examples
  - dry-run/preview workflow
  - conflict meaning and resolution guidance

### 9. Auth, Observability, and Safety

- Require KB access for all batch operations.
- Require write/admin scope for mutating import and read/search or admin scope for preview, matching project auth conventions.
- Log only low-cardinality safe fields: `kb_name`, row counts, action counts, result status, and trace id.
- Do not log raw document text, full CSV content, API keys, or high-cardinality labels like raw `manual_id` in metrics.
- Preserve existing `/search`, `/manuals`, `/manual-library`, single upload, metadata edit, and rebuild behavior.

## Acceptance Criteria

- [ ] Operators can submit a batch of documents plus JSON/JSONL/CSV metadata for one KB and receive a non-mutating validation preview.
- [ ] Preview rows include `manual_id`, `source_file`, `tag`, `status`, action, severity, and actionable messages.
- [ ] Batch validation detects per-row metadata errors, unsafe paths, unsupported suffixes, missing file/metadata pairs, duplicate `manual_id`, duplicate `source_file`, and existing-library conflicts.
- [ ] Batch commit can create valid manuals and mark the KB as pending rebuild without making changes searchable before rebuild.
- [ ] Create-only mode rejects existing manuals; upsert mode requires explicit overwrite approval.
- [ ] Filesystem writes are constrained to the manual library root and cannot path-traverse outside it.
- [ ] Admin UI supports multi-file plus metadata import, preview filtering, conflict display, and explicit import of valid/selected rows.
- [ ] Existing single-manual APIs and UI workflows remain backward compatible.
- [ ] Tests cover JSON, JSONL, and CSV parsing; validation preview; conflict detection; safe path handling; commit behavior; and UI route behavior.
- [ ] README and `product_manuals/README.md` document the bulk workflow and metadata templates.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- Unit and API tests cover batch parser, validator, preview, and commit behavior.
- UI tests or route-level tests cover the bulk import controls and static assets at an appropriate level.
- `uv run pytest tests/ -q` passes.
- Any durable backend conventions learned during implementation are added to `.trellis/spec/backend/`.

## Out of Scope

- Database-backed import sessions or durable audit history.
- Object storage/S3 multipart upload.
- OCR for scanned PDFs.
- Automatic LLM tag generation.
- Spreadsheet export with formatting beyond plain CSV.
- Multi-user collaborative import review.
- Cross-KB bulk import in a single request.
- Automatic rebuild by default.

## Follow-Up Ideas

- Saved import sessions with audit history.
- CSV export of preview errors for offline cleanup.
- Bulk metadata edit on existing manuals.
- Taxonomy management for approved tags/categories.
- Import progress streaming for very large batches.
