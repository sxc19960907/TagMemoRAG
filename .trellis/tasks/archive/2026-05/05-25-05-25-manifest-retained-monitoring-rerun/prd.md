# Manifest-driven retained monitoring rerun

## Goal

Allow the default-on retained monitoring manifest to rerun declared slice
commands before summarizing, while keeping execution explicit and bounded.

## Requirements

- Add rerun support for manifest slices that declare `rerun_command`.
- Keep default CLI behavior summary-only; rerun must require an explicit flag.
- Parse commands safely as argument lists, not with shell execution.
- Record rerun status in the bounded monitoring summary.
- Failed rerun commands must make the monitoring report fail with a clear
  bounded failed check.
- Keep stdout/stderr provider or source payloads out of committed reports.
- Add focused tests for successful rerun, failed rerun, summary-only default,
  and CLI behavior.

## Acceptance Criteria

- [ ] `scripts/default_on_retained_monitoring.py --rerun` executes declared
      manifest commands before summarizing.
- [ ] Summary-only behavior remains unchanged without `--rerun`.
- [ ] Rerun status is represented in JSON/Markdown output.
- [ ] Focused tests pass.
- [ ] Parent program log records the child result and next recommendation.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
