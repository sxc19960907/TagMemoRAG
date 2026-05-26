# Eval run user guidance

## Goal

Make exported feedback eval drafts easier to run and understand from the Retrieval Quality workflow, so a user can turn promoted feedback into a real regression check without guessing CLI flags.

## Requirements

- Preserve the current browser safety boundary: the Retrieval Quality page should guide the user to run eval, not execute a long-running eval job from the browser in this task.
- After promotion preview/export, show an eval run command that is valid for feedback eval drafts.
- The command must account for the current eval CLI requirement that `tagmemorag eval run` needs either `--docs` or `--reuse-built-kb`.
- The page should explain what the command validates and where the JSON report will be written.
- Export/preview summary should include the eval suite path and a suggested report path.
- Exported feedback eval draft JSONL must remain parseable by the existing `load_eval_suite` loader.
- Tests must verify the suggested command shape and that a feedback eval draft can be consumed by the eval runner path.
- Keep changes narrow to feedback promotion summary/guidance unless research proves a small CLI helper is needed.

## Acceptance Criteria

- [x] Promotion preview/export response includes a suggested eval command with `--reuse-built-kb` and `--output`.
- [x] Retrieval Quality page displays the eval suite path, report path, command, and short explanation in user-readable form.
- [x] Unit tests verify exported feedback eval drafts parse through `load_eval_suite` and command summary fields are present.
- [x] Browser test verifies Q&A feedback → expected evidence → export → eval guidance is visible and coherent.
- [x] Existing feedback promotion and Retrieval Quality tests remain passing.

## Outcome

- Promotion preview/export summary now includes `suite_path`, `report_path`, a shell-safe `next_command`, and `command_note`.
- The suggested command uses `--reuse-built-kb` and writes a JSON report next to the exported feedback suite.
- Retrieval Quality renders the suite path, report path, ready/skipped counts, eval command, and explanation.
- Tests cover normal paths and shell quoting for paths containing spaces.

## Notes

- Confirmed from code: `eval run` supports `--suite`, `--docs`, `--config`, `--output`, `--kb`, `--reuse-built-kb`, and threshold flags.
- Confirmed from `run_eval`: `--docs` is required unless `--reuse-built-kb` is set.
- Confirmed from e2e tests: eval run writes a JSON report and returns nonzero when thresholds fail.
- Out of scope for this task: browser-started eval jobs, background job queue, live report viewer, or changing ranking/eval semantics.
