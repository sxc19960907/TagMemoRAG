# Error Handling

> Error contracts for TagMemoRAG.

---

## Overview

All service-facing failures should use a structured error shape:

```json
{"code": "ERROR_CODE", "message": "Human readable message", "detail": {}}
```

`errors.py` owns the error code enum and exception types. API handlers convert project exceptions into the structured response format. Lower layers should raise project errors when the caller can act on the failure.

---

## Error Types

Define these in `errors.py`:

- `ErrorCode`: enum of stable service error strings.
- `ServiceError`: base exception with `code`, `message`, and `detail`.
- Specific subclasses where they improve readability, such as `KbNotLoadedError`, `RebuildInProgressError`, `RebuildFailedError`, `InvalidConfigError`, and `StorageVersionError`.

Expected M0 codes include:

- `KB_NOT_LOADED`
- `REBUILD_IN_PROGRESS`
- `REBUILD_FAILED`
- `INVALID_REQUEST`
- `INVALID_CONFIG`
- `STORAGE_LOAD_FAILED`
- `STORAGE_SCHEMA_MISMATCH`
- `ANCHOR_NOT_FOUND`

---

## Error Handling Patterns

- Pure functions should raise `ValueError` only for programmer errors or invalid direct arguments. Service boundary errors should be converted to `ServiceError` before reaching API responses.
- Storage load failures should include the path and schema/version detail when safe.
- Rebuild failures must not clear or replace the current graph. Keep serving the old `GraphState`.
- Concurrent rebuild attempts should fail fast with `REBUILD_IN_PROGRESS`.
- Anchor reconcile failures are not fatal when the graph is valid. Return unresolved anchors in rebuild or graph info responses.

---

## API Error Responses

FastAPI handlers must return the structured shape consistently:

```json
{
  "code": "REBUILD_IN_PROGRESS",
  "message": "A rebuild is already running.",
  "detail": {"task_id": "existing-task-id"}
}
```

Do not leak stack traces, local absolute paths outside the project, model internals, or raw document text in client errors.

---

## Common Mistakes

- Do not return ad hoc strings such as `"error": "failed"`.
- Do not let generic exceptions become FastAPI's default 500 body for known service failures.
- Do not swallow rebuild errors. Record them in the rebuild task status and preserve the previous graph.
- Do not make clients depend on exception class names; clients should depend on stable `code` values.
