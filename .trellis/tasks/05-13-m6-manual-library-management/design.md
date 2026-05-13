# design.md - M6 Manual Library Management Loop

## Scope

M6 adds a file-backed manual library management layer around the existing M5 ingestion path. It should not replace WAVE-RAG, graph persistence, anchor reconciliation, or metadata-aware search. It provides safer ways to manage source manuals and then uses the existing `build_kb()` pipeline to make those changes searchable.

## Current State

```text
source files + optional sidecar metadata
  -> build_kb(docs_dir, kb_name, cfg)
  -> parse_document(...)
  -> graph nodes with metadata
  -> save_kb(data/{kb_name}/graph.json + vectors.npz + anchors.json + meta.json)
  -> /search and /manuals read loaded GraphState
```

Key current files:

- `src/tagmemorag/manuals.py`: `ManualMetadata`, sidecar resolution, fallback metadata, tag normalization.
- `src/tagmemorag/state.py`: KB build/load/save and async rebuild task lifecycle.
- `src/tagmemorag/api.py`: `/search`, `/rebuild`, `/manuals`, `/kb`, anchors, cache clear.
- `src/tagmemorag/storage/atomic.py`: atomic file replacement helper.

## Target State

```text
manual library root for kb
  -> validate metadata
  -> upsert source + sidecar
  -> library manifest/pending marker
  -> list/detail managed manuals
  -> library rebuild
  -> existing build_kb(library_root, kb_name, cfg)
  -> current graph swap only after success
```

The graph remains the search-serving artifact. The manual library becomes the source-of-truth working set for future builds.

## Proposed Module Boundary

Add `src/tagmemorag/manual_library.py`.

Responsibilities:

- Resolve the safe library root for a KB.
- Validate relative source paths and document suffixes.
- Read/write source files and sidecar metadata.
- Maintain a lightweight manifest or pending marker.
- List managed manual records from files and sidecars.
- Exclude disabled manuals from build input using a build staging strategy.

Keep `manual_library.py` independent of FastAPI, CLI argument parsing, and global app state. `api.py` and `cli.py` orchestrate it.

## Configuration

Add config under `Settings`:

```python
class ManualLibraryConfig(BaseModel):
    root_dir: str = "product_manuals"
    allow_overwrite: bool = False
```

Recommended root layout:

```text
product_manuals/
  {kb_name}/
    coffee/
      coffee-machine.md
      coffee-machine.metadata.json
    .tagmemorag-library.json
```

Reasons:

- It preserves the existing product manual convention.
- It keeps source documents separate from generated `data/{kb_name}` artifacts.
- It lets `build_kb(library_root / kb_name, kb_name, cfg)` reuse M5 sidecar scanning.

If a project already points `/rebuild` to another docs root, that endpoint still works. Library-aware endpoints use `manual_library.root_dir`.

## Data Contracts

### ManualLibraryRecord

Recommended dataclass:

```python
@dataclass(frozen=True)
class ManualLibraryRecord:
    kb_name: str
    manual_id: str
    source_file: str
    metadata: ManualMetadata
    status: Literal["active", "disabled", "archived"]
    exists: bool
    checksum: str
    updated_at: str
    validation_errors: tuple[dict[str, object], ...] = ()
    chunk_count: int | None = None
    searchable: bool = False
    rebuild_required: bool = False
```

`status` should be stored in metadata as M5 already allows a `status` field. Active manuals are included in rebuilds. Disabled or archived manuals remain listed but are excluded.

### Library Manifest

Use a small JSON file at `.tagmemorag-library.json` per KB:

```json
{
  "schema_version": "1",
  "kb_name": "default",
  "pending_changes": true,
  "last_successful_build_id": "202605...",
  "updated_at": "2026-05-13T..."
}
```

The manifest tracks library-level state only. Per-manual truth stays in sidecar metadata and source files to avoid a second registry that can drift.

## API Design

### `POST /manuals/validate`

Request:

```json
{
  "kb_name": "default",
  "metadata": {
    "manual_id": "coffee-cm1-zh-cn-v1",
    "title": "Coffee CM1 manual",
    "source_file": "coffee/coffee-cm1.md",
    "product_category": "coffee",
    "language": "zh-CN",
    "tags": ["maintenance"]
  },
  "mode": "create"
}
```

Response:

```json
{
  "valid": true,
  "normalized": {...},
  "messages": []
}
```

Validation errors should use the existing structured service error response when the whole request is invalid. Field-level warnings/messages can be returned for UI display when the request shape is valid.

### `POST /manuals`

Use multipart form upload for the document plus a JSON `metadata` field, because source files may be PDFs.

Fields:

- `kb_name`
- `metadata`
- `file`
- `overwrite` default `false`
- `trigger_rebuild` default `false`

Response includes the `ManualLibraryRecord` and optional rebuild task.

### `PATCH /manuals/{manual_id}`

Update metadata and optionally replace source file. If using multipart for optional file replacement is awkward, use:

- `PATCH /manuals/{manual_id}/metadata` for JSON-only updates.
- `PUT /manuals/{manual_id}/file` for file replacement.

The implementation can choose the simpler tested shape, but docs should stay clear.

### `DELETE /manuals/{manual_id}`

Query:

- `kb_name`
- `hard=false`

Soft delete sets `status=disabled` or `archived`. Hard delete removes source and sidecar from the library root.

### `GET /manuals`

Preserve the current search-facing behavior by default. Add `source=graph|library` or create a separate route such as `GET /manual-library`.

Recommended for compatibility:

- Keep `GET /manuals` graph-derived.
- Add `GET /manual-library?kb_name=...` for managed library state.

## Rebuild Integration

Add `POST /manual-library/rebuild`:

```json
{"kb_name": "default"}
```

This resolves `manual_library.root_dir/{kb_name}` and calls existing `AppState.start_rebuild(...)`.

Disabled manual exclusion has two implementation options:

1. Modify `build_kb()` to skip source files whose loaded metadata status is not `active`.
2. Build from a temporary staging directory containing only active source/sidecar pairs.

Recommended: Option 1. It is simpler, avoids temporary copies of PDFs, and makes status semantics consistent for CLI builds too. It changes `build_kb()` behavior only for metadata with explicit inactive status.

On rebuild success, clear `pending_changes` in the manifest and store `last_successful_build_id`. On failure, leave pending changes true and preserve current graph.

## Cache and Anchors

- Manual mutations mark the library pending, but do not clear query cache immediately because the served graph has not changed yet.
- Existing rebuild and graph swap behavior changes `build_id`, causing cache misses naturally after successful rebuild.
- Existing anchor reconciliation should remap anchors by stable `anchor_key`; unresolved anchors remain visible via graph info.

## Error Model

Reuse existing codes where possible:

- `INVALID_INPUT`: invalid metadata, unsupported suffix, unsafe relative path.
- `INVALID_REQUEST`: malformed operation, missing file, unknown manual id.
- `FORBIDDEN`: scope or KB allowlist failure.
- `REBUILD_IN_PROGRESS`: library rebuild attempted while a KB rebuild is running.
- `REBUILD_FAILED`: build failure recorded in rebuild task.

Consider adding `MANUAL_NOT_FOUND` only if clients need to distinguish it from other invalid requests. If added, document it in `errors.py` and `.trellis/spec/backend/error-handling.md`.

## Storage Safety

- Use `Path.resolve()` checks to ensure all writes remain under the KB library root.
- Write sidecar metadata via `atomic_write()`.
- For uploaded source files, write to a temporary path under the same directory and replace atomically.
- Reject paths containing absolute paths, parent traversal, empty parts, or platform separators that normalize outside root.

## Tests

Unit tests:

- safe path resolution
- supported suffix validation
- metadata validation and normalization
- duplicate manual id detection
- manifest pending state
- disabled metadata skipped by `build_kb()`

API tests:

- validate endpoint success/failure
- upload create and conflict
- metadata update marks pending
- soft delete disables manual
- hard delete path safety
- library listing includes pending/unbuilt records
- library rebuild calls existing async path and preserves failure semantics

Regression tests:

- existing `/manuals` response remains compatible
- existing `/rebuild` with explicit `docs_dir` still works
- M5 filtered search still works after library rebuild

## Rollout / Rollback

Rollout:

- Add config defaults so existing deployments behave unchanged.
- Ship new endpoints alongside existing `/manuals` and `/rebuild`.
- Document that uploaded changes are not searchable until a successful rebuild.

Rollback:

- Disable use of the new endpoints; existing KB data under `data/{kb_name}` keeps serving.
- Because source files and sidecars stay compatible, operators can still run `tagmemorag build --docs product_manuals/{kb_name}` manually.
