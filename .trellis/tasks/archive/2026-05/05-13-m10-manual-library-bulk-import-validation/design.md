# design.md - M10 Manual Library Bulk Import and Validation

## Scope

M10 adds batch-oriented operations on top of the existing M6 manual library and M7 admin UI. It should not replace the single-manual APIs. The shared backend validation/import service should power API, UI, and optional CLI flows so CSV/JSON parsing and conflict semantics stay consistent.

## Current State

```text
single manual metadata/file
  -> POST /manuals/validate
  -> POST /manuals or PATCH /manuals/{manual_id}/metadata
  -> file-backed sidecar + source write
  -> pending marker
  -> POST /manual-library/rebuild
```

Key existing boundaries:

- `src/tagmemorag/manuals.py`: `ManualMetadata`, sidecar naming, tag normalization.
- `src/tagmemorag/manual_library.py`: safe library paths, records, validation, upload/update/delete, manifest pending state.
- `src/tagmemorag/api.py`: M6 JSON endpoints and M7 UI route.
- `src/tagmemorag/web/static/manual_library.js`: admin UI behavior.
- `src/tagmemorag/web/templates/manual_library.html`: admin UI shell.

## Target Flow

```text
documents + metadata JSON/JSONL/CSV
  -> parse candidates
  -> normalize ManualMetadata per candidate
  -> compare within batch
  -> compare against existing manual library
  -> return conflict preview
  -> explicit commit selected/valid rows
  -> write source + sidecar
  -> mark library pending rebuild
```

Preview is the important product boundary: operators should see what will happen before files are written.

## Proposed Module Boundary

Add `src/tagmemorag/manual_bulk_import.py`.

Responsibilities:

- Parse JSON, JSONL, and CSV metadata into batch candidates.
- Match metadata rows to uploaded documents.
- Run per-candidate metadata validation through existing `manual_library` / `ManualMetadata` logic.
- Detect intra-batch conflicts and existing-library conflicts.
- Produce a UI-friendly preview model.
- Commit validated candidates through existing `manual_library.upsert_manual()` behavior.

Keep this module independent of FastAPI request objects and template/UI state. `api.py`, `cli.py`, and the browser UI should orchestrate it.

## Data Contracts

### BulkImportCandidate

Recommended dataclass:

```python
@dataclass(frozen=True)
class BulkImportCandidate:
    row: int
    manual_id: str
    source_file: str
    metadata: ManualMetadata | None
    raw_metadata: dict[str, Any]
    uploaded_filename: str | None = None
    file_token: str | None = None
    parse_errors: tuple[ValidationMessage, ...] = ()
```

`file_token` can be a request-local key that API code maps to uploaded bytes. It should not be persisted as a long-lived storage key in M10 unless implementation chooses a staged temporary directory.

### BulkPreviewIssue

```python
@dataclass(frozen=True)
class BulkPreviewIssue:
    row: int
    manual_id: str | None
    source_file: str | None
    tag: str | None
    status: str | None
    action: Literal["create", "update", "skip", "conflict", "invalid"]
    severity: Literal["info", "warning", "error"]
    code: str
    message: str
```

The `tag` field is repeated per tag issue when useful. For row-level issues that are not tag-specific, `tag` can be `None` or an empty string.

### BulkImportPreview

```python
@dataclass(frozen=True)
class BulkImportPreview:
    kb_name: str
    mode: Literal["create_only", "upsert", "dry_run"]
    valid_count: int
    warning_count: int
    error_count: int
    create_count: int
    update_count: int
    skip_count: int
    rows: tuple[BulkPreviewIssue, ...]
    candidates: tuple[BulkImportCandidate, ...]
```

API responses should avoid returning raw file content. Returning normalized metadata per candidate is useful for UI, but large source payloads must stay request-local.

## Metadata Input Parsing

### JSON

Accept either:

```json
[
  {
    "manual_id": "fridge-nrk6192-zh-cn-v1",
    "title": "NRK6192 User Manual",
    "source_file": "fridge/nrk6192.pdf",
    "product_category": "fridge",
    "language": "zh-CN",
    "tags": ["temperature-setting", "maintenance"],
    "status": "active"
  }
]
```

or an object wrapper:

```json
{"manuals": [{ "...": "..." }]}
```

### JSONL

Each non-empty line is one metadata object. Report line numbers as `row`.

### CSV

Recommended columns:

```csv
manual_id,title,source_file,brand,product_category,product_name,product_model,language,version,tags,status,notes
```

Tag parsing:

- Split `tags` on comma, newline, or semicolon.
- Trim whitespace.
- Normalize through the existing tag normalization rule.
- Empty values become `[]`.

CSV parser should use the Python standard `csv` module, not ad hoc splitting.

## File Matching

Matching priority:

1. Exact `source_file` basename/path against uploaded relative path.
2. Exact uploaded filename against `Path(source_file).name`.
3. Optional explicit manifest mapping if API/UI adds one later.

If more than one uploaded file matches a metadata row, return an `AMBIGUOUS_FILE_MATCH` error and require the operator to fix the metadata or filenames.

If a metadata row has no uploaded file, allow preview to proceed but mark the row as invalid for create. For upsert metadata-only updates, this can become valid only if an existing manual with that `manual_id` or `source_file` exists and the operation explicitly allows metadata-only update.

## Conflict Detection

Run validation in layers:

1. Parse errors: malformed JSON/CSV, missing required columns, invalid row shape.
2. Metadata validation: existing `ManualMetadata.from_dict()` normalization and safe metadata rules.
3. File validation: suffix support, uploaded file match, safe relative path.
4. Intra-batch validation:
   - duplicate `manual_id`
   - duplicate `source_file`
   - conflicting metadata for same target
   - uploaded file without metadata
5. Existing-library validation:
   - target `manual_id` already exists
   - target `source_file` already exists
   - status transition from disabled/archived to active
   - overwrite/upsert approval missing

Every issue should include a stable `code` and an operator-readable `message`.

## API Design

### `POST /manual-library/bulk/preview`

Multipart form:

- `kb_name`
- `metadata_format`: `json`, `jsonl`, or `csv`
- `metadata`: uploaded file or text field
- `files`: zero or more document uploads
- `mode`: `create_only`, `upsert`, or `dry_run`

Response:

```json
{
  "kb_name": "default",
  "mode": "create_only",
  "summary": {
    "valid_count": 12,
    "warning_count": 2,
    "error_count": 1,
    "create_count": 12,
    "update_count": 0,
    "skip_count": 1
  },
  "rows": [
    {
      "row": 3,
      "manual_id": "fridge-nrk6192-zh-cn-v1",
      "source_file": "fridge/nrk6192.pdf",
      "tag": "temperature-setting",
      "status": "active",
      "action": "create",
      "severity": "info",
      "code": "READY",
      "message": "Ready to import."
    }
  ],
  "normalized": [...]
}
```

If M10 avoids persistent upload staging, this endpoint is purely preview and cannot be followed by a separate commit that references uploaded files. In that simpler model, the commit endpoint receives the same multipart payload plus `commit=true`.

### `POST /manual-library/bulk/import`

Recommended simple shape for M10: accept the same multipart request as preview, plus:

- `mode`
- `overwrite`
- `selected_rows` optional JSON array of row numbers
- `trigger_rebuild` default `false`

The endpoint reruns preview internally before writing. It must reject import when any selected row has `severity=error`.

Response:

```json
{
  "kb_name": "default",
  "imported_count": 12,
  "skipped_count": 1,
  "failed_count": 0,
  "pending_rebuild": true,
  "records": [...]
}
```

Rerunning preview in the import request prevents stale preview decisions from being used after the library changed.

## Commit Semantics

- `create_only`: only rows whose action is `create` can be imported.
- `upsert`: rows whose action is `create` or approved `update` can be imported.
- `dry_run`: never writes.
- `selected_rows`: when absent, import all valid rows; when present, import only selected valid rows.
- Rows with warnings can be imported unless the warning code is documented as blocking.
- Any mutating success marks the library pending.

Filesystem behavior should reuse M6 source/sidecar writes. The batch service coordinates order and error collection; it should not invent a second storage path.

## UI Design

Extend the M7 page with a bulk import panel or modal:

- File input accepting multiple documents.
- Metadata input accepting `.json`, `.jsonl`, `.csv`, or pasted text.
- Mode segmented control: create-only / upsert / dry-run.
- Preview button.
- Preview table columns:
  - row
  - manual_id
  - source_file
  - tag
  - status
  - action
  - severity
  - message
- Filters:
  - severity
  - action
  - status
  - tag text
- Import valid / import selected action.

Keep the bulk UI compact and operational. Avoid adding a separate frontend framework for M10.

## Auth and Observability

- Preview requires KB access and the same read/admin posture as metadata validation.
- Import requires the same write/admin scope as single-manual upload.
- Logs:
  - `kb_name`
  - format
  - total rows/files
  - create/update/skip/error counts
  - request trace id
- Metrics should use low-cardinality counts only. Do not label metrics by manual id, source file, tag, or raw status values beyond a bounded enum.

## Rollout / Rollback

Rollout:

- Add backend service and tests.
- Add preview/import endpoints.
- Add UI controls.
- Document templates and workflow.

Rollback:

- Hide or remove bulk UI controls and endpoints. Existing M6/M7 single-manual workflows continue to work.
- No graph format migration is needed.

## Open Design Notes

- If large upload batches become slow, follow up with durable staged import sessions. M10 can start with request-local parsing and commit to keep persistence simple.
- CSV export of preview errors is useful but not required for MVP.
- Import progress streaming is deferred; response can be synchronous for modest batch sizes.
