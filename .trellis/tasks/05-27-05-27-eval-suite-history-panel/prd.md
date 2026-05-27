# Eval Suite History Panel PRD

## Problem

Browser-first RAG evaluation can now run predefined fixture suites and Retrieval Quality feedback drafts, but users still need to infer suite state from a selector plus separate recent report cards. This makes it hard to answer: which suites exist, which one ran last, whether it passed, and which report to open.

## Goals

- Show a clear, read-only suite history panel on the Eval Report admin page.
- For each browser-safe eval suite, show kind, case count, run mode, updated time, and the latest matching report when available.
- Let the user select/run a suite and open/load the latest report without using CLI commands.
- Keep all discovery bounded to existing project/report roots and feedback draft roots.
- Preserve existing eval run behavior and report viewer behavior.

## Non-Goals

- Do not delete, archive, edit, or rename eval draft files.
- Do not add arbitrary filesystem browsing or arbitrary command execution.
- Do not change retrieval ranking, eval scoring, thresholds, or report payload schemas beyond additive suite metadata.

## Acceptance Criteria

- `GET /eval/suites` returns each suite with additive latest-report metadata when a matching report exists.
- The matching report metadata contains only bounded summary fields: report path, relative path, modified time, pass/fail status, case count, and failed count.
- The Eval Report page renders a suite history/management panel with select, run, open latest, and load latest actions.
- Existing run launcher, recent reports list, and case report viewer continue to work.
- Unit tests cover suite latest-report matching and static asset/template wiring.
- JS syntax checks and targeted Python tests pass.
