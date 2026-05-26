# Design: Eval run user guidance

## Current Contracts

- `tagmemorag eval run --suite <path>` loads JSONL cases via `load_eval_suite`.
- `run_eval` requires `--docs` unless `--reuse-built-kb` is set.
- `EvalReport.write_json` writes a JSON report when `--output` is supplied.
- Feedback promotion summary already returns `output_path` and a basic `next_command`.

## Proposed Contract

Extend `EvalPromotionPreview.to_dict()["summary"]` with:

- `suite_path`: same as promotion `output_path`.
- `report_path`: default report path next to the suite, using the suite stem plus `-report.json`.
- `next_command`: `tagmemorag eval run --suite <suite_path> --reuse-built-kb --output <report_path>`.
- `command_note`: short explanation that this checks the exported feedback cases against the currently built KB.

The UI renders these fields as an eval draft guidance card. Raw JSON remains visible.

## Why `--reuse-built-kb`

Feedback exported from Retrieval Quality is tied to an already built KB and may not know the original docs path. `--reuse-built-kb` is the safest default command for a browser workflow. Users who want isolated rebuild evals can replace it with `--docs <path>`.

## Boundaries

- Do not execute eval from the browser in this task.
- Do not change eval scoring or thresholds.
- Do not change the eval JSONL case schema.
- Keep feedback promotion export behavior compatible with existing CLI/API callers.

## Rollback

Rollback is limited to summary fields and UI rendering. Existing `cases`, `skipped`, and `output_path` fields remain unchanged.
