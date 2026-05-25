# Bulk Import Severity Alignment

## Goal

Align manual-library bulk import preview severity with metadata validation
severity so non-blocking metadata hints do not appear as blocking errors.

## Source Evidence

- `docs/production-provider-e2e-pilot.md` records a production pilot follow-up:
  multi-tag metadata triggered `TAG_ORDERING_HINT`; metadata validation treats it
  as non-blocking info, but bulk preview reports it as an error.
- `validate_metadata` already uses `ValidationMessage.detail["severity"]` for
  non-blocking messages such as `info` and `warning`.

## Requirements

- Preserve blocking behavior for true parse, path, duplicate, suffix, conflict,
  and missing-upload errors.
- Bulk preview must map validation messages with `detail.severity == "info"` to
  `severity="info"`.
- Bulk preview must map validation messages with `detail.severity == "warning"`
  to `severity="warning"`.
- `UNKNOWN_COLUMN` remains a non-blocking warning.
- Non-blocking validation messages must not reduce `valid_count`, must not add
  to `error_count`, and must not prevent selected rows from being imported.
- No API response schema changes.

## Acceptance Criteria

- [x] Bulk preview reports `TAG_ORDERING_HINT` as `info`.
- [x] A row with only `TAG_ORDERING_HINT` remains ready/importable.
- [x] Bulk import can commit a selected row that has only non-blocking metadata
      messages.
- [x] Existing bulk import API/table shape remains unchanged.
- [x] Focused manual library bulk import tests pass.

## Rollback

Revert the severity-mapping helper and tests; previous conservative error
classification returns.
