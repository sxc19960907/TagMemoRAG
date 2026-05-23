# CLI Complete Split Implementation Plan

1. [x] Create parser and dispatch modules.
2. [x] Move remaining command execution branches into focused command modules.
3. [x] Reduce `cli.py` to `main(argv)` plus the module entry point.
4. [x] Update tests to patch new command-owner modules where needed.
5. [x] Update directory structure spec with the final CLI module boundaries.
6. [x] Run focused then full CLI tests:
   - `tests/unit/test_cli.py`
   - `tests/unit/test_cli_helpers.py`
   - `tests/unit/test_cli_feedback.py`
   - `tests/unit/test_cli_source_import.py`
   - `tests/unit/test_cli_provider.py`
   - `tests/unit/test_cli_production_provider_verify.py`

## Rollback Points

- If parser extraction breaks many command tests, keep parser in `cli.py` and
  complete execution extraction first.
- If a command module creates import cycles, move shared helper functions into
  `cli_helpers.py` or a narrower command module instead of importing `cli.py`.
