# Bulk Import Severity Alignment — Implementation Plan

## Steps

1. Add focused failing tests in `tests/unit/test_manual_bulk_import.py`:
   - preview maps multi-tag `TAG_ORDERING_HINT` to info;
   - preview still includes `READY`;
   - commit selected row with only the hint succeeds.
2. Update `_issue_from_message` in `src/tagmemorag/manual_bulk_import.py` to
   respect `ValidationMessage.detail["severity"]`.
3. Run focused validation:

```bash
uv run pytest tests/unit/test_manual_bulk_import.py tests/unit/test_manual_bulk_import_api.py tests/unit/test_manual_library.py
git diff --check
```

4. Run broader unit/e2e validation if focused checks are green:

```bash
uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py
```

## Exit Criteria

- [x] Bulk preview reports `TAG_ORDERING_HINT` as `info`.
- [x] A row with only `TAG_ORDERING_HINT` remains ready/importable.
- [x] Bulk import can commit a selected row that has only non-blocking metadata
      messages.
- [x] Existing bulk import API/table shape remains unchanged.
- [x] Focused manual library bulk import tests pass.
