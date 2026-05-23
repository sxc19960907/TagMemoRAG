# CLI Complete Split

## Goal

Finish the `src/tagmemorag/cli.py` slimming effort in one cohesive task by turning
`cli.py` into a thin package entry point and moving parser construction plus
remaining command execution logic into focused modules.

## Requirements

- Preserve all existing CLI commands, flags, stdout/stderr behavior, report
  writing behavior, and exit codes.
- Keep `tagmemorag.cli.main(argv)` and `python -m tagmemorag ...` as the stable
  public entry points.
- Move argparse construction out of `cli.py` into a focused parser module.
- Move remaining command execution branches out of `cli.py` into focused command
  modules. Previously extracted command modules may remain and be reused.
- After this task, `cli.py` should contain only the minimal entry-point wrapper
  and no command-specific business logic.
- Avoid import cycles: command modules may import lower-level services, but
  should not import `tagmemorag.cli`.
- Preserve test monkeypatch seams by moving tests to patch the focused command
  modules rather than `tagmemorag.cli` for extracted logic.
- Leave unrelated untracked files untouched.

## Acceptance Criteria

- [x] `cli.py` is a thin wrapper around parser construction and command dispatch.
- [x] Parser construction lives outside `cli.py`.
- [x] Remaining command execution for build/search/serve/config/langchain,
  retrain-residuals, eval/answer-quality, auth, manual-bulk/manual-library/tag,
  qdrant, readiness, pilot, and epa lives outside `cli.py`.
- [x] Existing CLI behavior is preserved for subprocess and direct `cli.main`
  tests.
- [x] Full CLI-focused test suite passes.
- [x] Directory-structure spec records the new CLI module boundaries.

## Notes

This task intentionally supersedes the earlier one-command-group-at-a-time
approach. It should complete the current `cli.py` split rather than creating
another series of small extraction tasks.
