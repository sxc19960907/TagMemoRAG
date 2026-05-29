# Clean demo workspace option

## Goal

Make the documented browser demo path reliable for first-time users even when `.tmp/tagmemorag-qa-demo` already contains stale local data from prior runs.

## Requirements

- Add an explicit clean/reset option to the `tagmemorag demo library-qa` command.
- The clean option must remove only the configured demo-local workspace paths needed by `examples/config/qa-demo.yaml`; it must not delete arbitrary user data outside those configured local paths.
- The default command behavior should remain backward compatible unless the user opts into cleaning.
- The command output should tell operators when cleanup happened.
- Update quick-start documentation to recommend the clean path for first-run or black-box verification.
- Add focused tests for argument parsing and clean behavior.

## Acceptance Criteria

- [x] `uv run python -m tagmemorag demo library-qa --clean ...` produces a clean demo KB with only the seeded demo manual.
- [x] Existing `demo library-qa` behavior without `--clean` remains compatible.
- [x] Tests cover CLI parsing and cleanup scope.
- [x] Browser quick-start docs mention the clean option.

## Verification Notes

- Added `--clean` to `tagmemorag demo library-qa`.
- Cleanup only removes configured relative paths under `.tmp/tagmemorag-qa-demo/...`; absolute paths and other `.tmp` directories are ignored.
- The demo JSON includes `cleanup.enabled` and `cleanup.removed`.
- Verified with:
  - `uv run pytest tests/unit/test_cli.py tests/unit/test_documentation_handoffs.py -q`
  - `uv run python -m tagmemorag demo library-qa --config examples/config/qa-demo.yaml --clean --output .tmp/tagmemorag-qa-demo/library-qa-response.json`
