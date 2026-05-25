# Bulk Import Severity Alignment — Design

## Scope

Change only the conversion from `ValidationMessage` to `BulkPreviewIssue` in
`manual_bulk_import.py`. Metadata validation already carries the desired
severity semantics.

## Current Behavior

`validate_metadata` treats messages with `detail.severity in {"info",
"warning"}` as non-blocking. Bulk import calls `validate_metadata` but then
converts every message except `UNKNOWN_COLUMN` into an error, losing that
semantic.

## Proposed Behavior

Add a small helper that resolves preview severity from a validation message:

- `detail.severity == "info"` -> `info`
- `detail.severity == "warning"` -> `warning`
- `UNKNOWN_COLUMN` -> `warning`
- everything else -> `error`

The existing `_ready_rows` logic already keys off `severity == "error"`, so
mapping the hint to `info` should automatically keep the row valid and
selectable.

## Compatibility

- No public schema changes.
- No config or dependency changes.
- Existing error rows remain blocking.
- UI filtering already supports `info`, `warning`, and `error`.

## Tests

- Unit test for `TAG_ORDERING_HINT` info preview row plus `READY` row.
- Unit test that commit succeeds for a selected row with only the hint.
- Existing API shape test remains green.
