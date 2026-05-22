# API CLI Entry Point Slimming

## Goal

Reduce future growth pressure in `src/tagmemorag/api.py` and `src/tagmemorag/cli.py` with a first low-risk extraction pass that preserves public behavior.

## Requirements

- Keep external FastAPI routes, request/response schemas, CLI commands, CLI flags, stdout/stderr behavior, and exit codes unchanged.
- Do not introduce new production dependencies.
- Prefer moving pure helpers or small handler-independent utilities before moving route or command orchestration.
- Preserve dependency direction: extracted modules may be imported by `api.py` or `cli.py`, but must not import FastAPI app globals, CLI `main`, or mutable global app state unless the module explicitly owns that runtime concern.
- The first extraction should target code with low coupling and focused existing tests:
  - QA short-context normalization/meta helpers currently in `api.py`.
  - Reusable CLI parser/file helper functions currently in `cli.py`.
- Add or preserve focused unit tests for moved helpers where behavior is user-facing or easy to regress.
- Leave unrelated untracked files untouched.

## Acceptance Criteria

- [x] `api.py` has fewer lines and delegates QA context formatting to a focused module outside the entry point.
- [x] `cli.py` has fewer lines and delegates reusable parser/file helpers to a focused module outside the entry point.
- [x] Existing imports and tests that intentionally use entry-point helpers either continue through compatibility wrappers or are updated to the new narrow module.
- [x] Focused API/CLI tests pass, including QA answer context behavior and CLI parser/command behavior touched by the extraction.
- [x] `api.py` and `cli.py` public behavior is unchanged.

## Notes

This is intentionally not a full router/command split. Larger moves such as APIRouter modules or command-handler packages should happen after this first extraction proves the pattern.
