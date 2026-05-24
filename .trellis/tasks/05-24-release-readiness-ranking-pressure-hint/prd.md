# Release readiness ranking pressure hint

## Goal

Surface optional general-web ranking-pressure diagnostics in release readiness
next steps without changing release gate status.

Release readiness is currently `passed`, but the new ranking-pressure diagnostic
shows two non-blocking GitHub cases where expected evidence is reachable yet
under-ranked. This task should keep that signal visible for future quality work
while preserving the clean release baseline.

## Confirmed Facts

- `scripts/diag_general_web_ranking_pressure.py` emits
  `general_web_ranking_pressure.v1` reports.
- Current retained report shows `ranking_pressure_count=2`.
- These items are not release blockers and should not turn a passed readiness
  report into warning/failed.
- Existing release readiness already supports configurable report paths through
  `DEFAULT_REPORT_PATHS` and `scripts/release_readiness.py --report name=path`.

## Requirements

- Add an optional `general_web_ranking_pressure` report path to release
  readiness.
- If the optional report exists and has `ranking_pressure_count > 0`, include
  bounded detail in the relevant stage and add a next-step hint.
- Do not change aggregate release status from `passed` to `warning`.
- If the optional report is missing, unreadable, or malformed, do not fail
  release readiness; include no hint.
- Do not include raw query text, snippets, or `actual_top_k` in readiness output.
- Preserve existing CLI behavior and report override support.

## Acceptance Criteria

- [ ] Clean readiness reports remain `passed`.
- [ ] When a ranking-pressure report is supplied, output includes
      `ranking_pressure_count` and highest pressure count.
- [ ] Passed readiness next steps mention non-blocking ranking pressure when
      present.
- [ ] Missing optional ranking-pressure report does not fail readiness.
- [ ] Unit tests cover present and missing optional report behavior.

## Notes

- This is a small release-reporting task, not a retrieval change.
