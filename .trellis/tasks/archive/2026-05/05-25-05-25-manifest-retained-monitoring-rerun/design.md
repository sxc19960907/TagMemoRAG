# Design

## Boundary

This task adds optional execution of manifest-declared rerun commands. It does
not invent new eval behavior and does not fetch remote corpora.

## Execution Model

- `run_default_on_retained_monitoring(..., rerun=False)` keeps existing
  summary-only behavior.
- `rerun=True` executes only slices that define `rerun_command`.
- Commands are parsed with `shlex.split` and run with `shell=False`.
- Output streams are captured but not persisted into the report.
- The report records slice name, status, and return code only.

## Failure Model

- Any non-zero rerun return code makes the final report `failed`.
- Summary checks still run after rerun attempts so operators get the most
  complete bounded state available.
- Failed checks use low-cardinality names such as
  `rerun:mixed_domain:exit_1`.
