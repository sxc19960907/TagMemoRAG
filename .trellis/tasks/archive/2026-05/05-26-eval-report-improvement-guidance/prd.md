# Eval report improvement guidance

## Goal

Turn the eval report viewer from a passive results page into an actionable RAG improvement assistant. When an operator opens a failed eval report, each problem case should explain what likely failed and what to do next, using deterministic signals already present in the eval report.

## Confirmed Facts

- The current `/eval/report` endpoint summarizes eval JSON reports and sorts failed/high-severity cases first.
- Case payloads include `metrics`, `failures`, `expected`, `actual_top_k`, `matched_expected_indexes`, `negative_hits`, `search_strategy`, and run context.
- The current UI shows failures, expected evidence, actual results, thresholds, and config snapshot, but it does not translate those signals into recommended actions.
- The browser should not run eval or mutate reports in this task.

## Requirements

- Add deterministic per-case guidance to the eval report API response.
- Guidance must classify common failure modes:
  - no expected evidence matched in retrieved results.
  - partial recall for multi-evidence cases.
  - expected evidence appears but too low in the ranking.
  - negative evidence was retrieved.
  - explicit threshold failure.
  - missing or weak expected matcher data.
- Each guidance item must include a concise diagnosis label, severity, explanation, and next action text.
- The report summary must include aggregate guidance counts so users can see the dominant issue type.
- The browser page must show the guidance prominently on each case and remain readable in Chinese/English UI mode.
- Existing eval report JSON format and eval CLI behavior must remain unchanged.

## Acceptance Criteria

- [ ] `/eval/report` case summaries include `guidance` and `primary_issue` fields.
- [ ] `/eval/report` top-level payload includes guidance counts grouped by issue code.
- [ ] The eval report UI renders diagnosis cards for failed/review cases.
- [ ] Unit tests cover no-match, partial-recall, low-rank, negative-hit, and weak-matcher guidance.
- [ ] Browser smoke confirms guidance is visible on a loaded report.
- [ ] Static JS checks and relevant pytest suites pass.

## Out of Scope

- LLM-generated advice.
- Running eval jobs from the browser.
- Editing eval fixtures or feedback records from the report page.
- Automatically changing retrieval/search configuration.
