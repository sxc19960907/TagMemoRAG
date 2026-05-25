# ManualsLib OpenCLI batch import

## Goal

Let operators use the local OpenCLI ManualsLib adapter to select real manual URLs, then batch-import those URLs into TagMemoRAG through the existing explicit `manualslib import-url` path.

## Requirements

- Add a project CLI command that invokes `opencli manualslib list` with operator-supplied brand/category/limit arguments.
- Reuse `import_manualslib_url` for each returned manual URL instead of duplicating page extraction or materialization logic.
- Keep the workflow bounded and operator-directed; do not crawl unbounded brand pages.
- Support a preview mode that prints the manuals OpenCLI found without importing them.
- Emit structured JSON with imported, skipped, and failed rows so a user can see which manuals were materialized.
- Handle missing or failing OpenCLI cleanly with a non-zero CLI exit instead of a traceback.
- Keep unit tests network-free by mocking the OpenCLI subprocess and URL importer.
- Preserve the prior explicit URL import command.

## Acceptance Criteria

- [x] `python -m tagmemorag manualslib import-opencli --brand hisense --category Dryer --limit N --output-dir <dir>` imports URLs returned by OpenCLI.
- [x] `--preview` returns discovered rows without calling the importer.
- [x] Duplicate URLs from OpenCLI are imported once and reported as skipped.
- [x] OpenCLI command failures are surfaced as a JSON/reportable CLI error path.
- [x] Unit tests cover preview, import, duplicate skip, and OpenCLI failure behavior.
- [x] Focused CLI/manualslib tests pass.

## Result

Added `manualslib import-opencli`, which shells out to `opencli manualslib list -f json`, optionally previews discovered manuals, deduplicates URLs, and imports selected rows through the existing explicit URL importer.

Validation:

- `.venv/bin/python -m pytest tests/unit/test_manualslib_import.py tests/unit/test_cli.py -q`: 32 passed.
- `.venv/bin/python -m compileall -q src/tagmemorag`: passed.
- Real OpenCLI preview against Hisense Dryer returned 3 manuals.
- Real smoke import with `--limit 1 --max-pages 1` materialized `manualslib-hisense-hdge80h` under `.tmp/manualslib-opencli-smoke`.
