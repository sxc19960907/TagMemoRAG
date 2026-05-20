# Final integration verification

## Goal

Run the repository's merge-facing verification after the pilot/eval policy work, record the result, and leave the branch in a clean handoff state.

## Requirements

- Run the same deterministic test command used by GitHub Actions for this repo.
- Verify the working tree is clean except for this task's own Trellis bookkeeping before finish.
- Fix only small regressions discovered by verification; do not add new product features.
- Record exact verification commands and outcomes in the task artifact.

## Acceptance Criteria

- [ ] `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py` passes, or any failure is documented with a concrete blocker.
- [ ] `git diff --check` passes.
- [ ] No active Trellis tasks remain after archive.
- [ ] Worktree is clean after commit/archive/journal.

## Out of Scope

- Pushing to remote or opening a PR unless the user explicitly asks.
- Squashing/rebasing the branch.
- Running live provider tests that require credentials/network-side effects.
