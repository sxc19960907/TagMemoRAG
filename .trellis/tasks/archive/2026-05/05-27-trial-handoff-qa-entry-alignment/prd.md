# Trial handoff QA entry alignment

## Goal

Align the trial handoff and quick-start documentation with the current browser-first QA entry path after the QA first-run guidance work.

## User Value

A trial operator or normal browser user should be able to follow the docs without remembering recent implementation details: open the QA page, understand the seeded-demo path, use the new empty-KB upload-first path, and know which local/browser checks are evidence versus which GitHub CI checks are external follow-up.

## Confirmed Facts

- `/qa?kb_name=default` now supports an empty-KB first-run state with upload-first guidance.
- QA-page upload can index a manual and replace static suggestions with uploaded-manual suggestions.
- Rebuild failure from QA-page upload links to RAG Readiness and Manual Library.
- Existing docs already cover seeded demo startup, Manual Library upload, retained pilot reports, and CI boundaries, but they do not yet describe the QA-page first-run upload path.
- `docs/trial-operator-handoff-2026-05-27.md` still contains an older GitHub push status line.

## Requirements

- Update the browser quick start to describe both supported user starts:
  - seeded demo manual path;
  - empty/new KB path directly from the QA page.
- Update trial operator handoff to reflect the current local state without hard-coding a stale pushed commit.
- Update retained trial/CI handoff or final review wording if needed so browser QA evidence and GitHub CI responsibility remain clear.
- Keep this documentation-only; do not change RAG runtime behavior.
- Preserve existing local verification commands and add doc assertions where they protect the updated handoff.

## Acceptance Criteria

- [x] Browser RAG Quick Start documents the QA-page first-run upload path.
- [x] Trial Operator Handoff no longer claims an outdated pushed commit as current state.
- [x] Documentation tests assert the updated handoff references the QA first-run path and current CI boundary.
- [x] Focused documentation tests pass.
- [x] `uv run python -m tagmemorag readiness browser-qa` passes.
- [x] `git diff --check` passes.

## Verification Notes

- `uv run pytest tests/unit/test_documentation_handoffs.py tests/unit/test_production_pilot.py -q` passed with 13 tests.
- `uv run python -m tagmemorag readiness browser-qa` passed.
- `git diff --check` passed.

## Spec Update Review

No `.trellis/spec/` update is needed. This task only aligns operator/user documentation with existing browser behavior and does not add or change API, CLI, persistence, or runtime contracts.

## Out Of Scope

- New UI behavior, API changes, or browser automation changes.
- GitHub push or PR creation.
- Rewriting all historical release documents.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
