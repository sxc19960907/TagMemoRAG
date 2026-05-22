# CLI Source Import Command Extraction

## Goal

Continue slimming `src/tagmemorag/cli.py` by moving source-import command execution for ManualsLib and public web sampling into a focused CLI command module without changing user-visible CLI behavior.

## Requirements

- Preserve all existing `tagmemorag manualslib ...` and `tagmemorag knowledge sample-web` commands, flags, stdout/stderr JSON shape, and exit codes.
- Keep parser registration in `cli.py` for now; move only command execution logic for the source-import command groups.
- Extract implementation into a focused module outside `cli.py` that can be unit-tested independently.
- Preserve ManualsLib OpenCLI error serialization, generic ManualsLib import error behavior, and public web ValueError failure JSON.
- Do not change manualslib/public-web importer APIs or output schemas.
- Leave unrelated untracked files untouched.

## Acceptance Criteria

- [x] `cli.py` delegates `args.command == "manualslib"` and `args.command == "knowledge"` execution to a focused module and has fewer lines.
- [x] The extracted module owns ManualsLib import-url/import-opencli and knowledge sample-web dispatch.
- [x] Existing CLI tests for ManualsLib and knowledge sample-web pass unchanged.
- [x] Direct tests cover at least one extracted module dispatch/failure path.
- [x] No API route behavior changes.
