# Deployment Pilot Readiness Pass

## Goal

Make the local pilot gate better match a real browser-first RAG trial by letting operators retain both backend pilot evidence and browser QA readiness evidence in one report.

## User Value

Before handing TagMemoRAG to a user for local trial, the operator should be able to run one bounded command that verifies config, backend RAG composition, answer/eval health, and the normal browser QA journey. The result should be reviewable without requiring the operator to stitch together several terminal outputs.

## Confirmed Facts

- `pilot run` already produces retained JSON/Markdown reports for config validation, provider probes, readiness smoke, answer-quality diagnostics, eval, and optional eval reauthoring diagnosis.
- `readiness browser-qa` already verifies the key browser path: demo manual, Manual Library, Q&A, citations, feedback, Retrieval Quality, eval draft/export, and browser eval launch.
- Existing docs tell operators to run both kinds of checks, but the retained pilot report does not include browser readiness.
- GitHub push remains deferred until the user asks to retry.

## Requirements

- Add an explicit `pilot run` option to include browser QA readiness.
- The browser stage must run focused mode by default and support full browser suite mode.
- Browser readiness results must appear as a normal pilot stage in JSON and Markdown reports.
- A browser readiness failure must fail the pilot report; a launch/runtime error must also fail the pilot report with a safe error summary.
- Preserve existing `pilot run` behavior unless the new option is provided.
- Update focused unit tests and operator docs.

## Acceptance Criteria

- [ ] `pilot run --include-browser-qa` adds a `browser_qa_readiness` stage.
- [ ] `pilot run --include-browser-qa --browser-qa-full` uses full browser readiness mode.
- [ ] Existing `pilot run` output remains unchanged when the browser flag is omitted.
- [ ] Unit tests cover pass, failure, and CLI wiring for the browser stage.
- [ ] Docs show the combined local pilot command and when to use it.
- [ ] Focused validation commands pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
