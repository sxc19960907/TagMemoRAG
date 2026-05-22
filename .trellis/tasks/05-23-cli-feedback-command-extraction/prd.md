# CLI Feedback Command Extraction

## Goal

Continue slimming `src/tagmemorag/cli.py` by moving the feedback command execution branch into a focused CLI command module without changing user-visible CLI behavior.

## Requirements

- Preserve all existing `tagmemorag feedback ...` commands, flags, stdout/stderr JSON shape, and exit codes.
- Keep parser registration in `cli.py` for now; move only command execution logic for the feedback command group.
- Extract implementation into a focused module outside `cli.py` that can be unit-tested independently.
- Do not change retrieval feedback service APIs or storage formats.
- Preserve compatibility with existing tests and leave unrelated untracked files untouched.

## Acceptance Criteria

- [x] `cli.py` delegates `args.command == "feedback"` execution to a focused module and has fewer lines.
- [x] The extracted module owns submit/list/review/promote-preview/promote dispatch for feedback commands.
- [x] Existing `test_cli_feedback_workflow` passes unchanged.
- [x] Broader CLI tests touched by command dispatch pass.
- [x] No API route behavior changes.
