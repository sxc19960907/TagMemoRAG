# CLI Production Provider Command Extraction

## Goal

Continue slimming `src/tagmemorag/cli.py` by moving provider and production-provider command execution into a focused CLI command module without changing user-visible CLI behavior.

## Requirements

- Preserve existing `tagmemorag provider probe` and `tagmemorag production-provider smoke|verify` commands, flags, stdout/stderr output, report-writing behavior, and exit codes.
- Keep parser registration in `cli.py` for now; move only command execution logic.
- Extract implementation into a focused module outside `cli.py` with direct unit coverage for at least one dispatch path.
- Preserve exception-to-exit-code behavior for production-provider smoke and verify.
- Do not change provider probe, production smoke, production verify, or pilot service APIs.
- Leave unrelated untracked files untouched.

## Acceptance Criteria

- [x] `cli.py` delegates provider command execution to a focused module and has fewer lines.
- [x] Extracted module owns `provider probe`, `production-provider smoke`, and `production-provider verify` execution.
- [x] Existing CLI tests for provider and production-provider commands pass.
- [x] Direct tests cover extracted module dispatch behavior.
- [x] No API route behavior changes.
