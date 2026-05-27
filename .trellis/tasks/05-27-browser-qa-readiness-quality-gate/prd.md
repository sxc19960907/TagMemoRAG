# Browser QA Readiness Quality Gate

## Goal

Define and implement a browser-first QA readiness gate so normal-user RAG flows are checked consistently before future changes are considered stable.

## User Value

Future changes to retrieval, answer formatting, manual library, or QA UI should not silently break the real browser path that a normal user experiences. The project needs one memorable gate that exercises the QA page, not only backend smoke checks.

## Confirmed Facts

- `python -m tagmemorag readiness smoke` already checks deterministic backend composition.
- Browser QA coverage exists in `tests/integration/test_browser_admin_ui.py`, but running it requires remembering `TAGMEMORAG_RUN_BROWSER_UI=1` and a long pytest target.
- The most important normal-user path is `test_browser_manual_library_to_qa_user_flow`.
- Full browser UI coverage is useful before releases, but too broad as the default per-change QA gate.

## Requirements

- Add a browser QA readiness command that wraps the existing Playwright pytest coverage.
- Default the command to the normal-user library-to-QA flow.
- Support an option to run the full browser UI suite when desired.
- Print a bounded JSON report with command, status, return code, duration, and test target.
- Return `0` on pass, `1` on test failure, and `2` when the test runner cannot be launched.
- Document how this gate relates to `readiness smoke`.

## Acceptance Criteria

- [ ] `python -m tagmemorag readiness browser-qa` runs the focused QA browser flow.
- [ ] `python -m tagmemorag readiness browser-qa --full` runs the full browser UI integration file.
- [ ] The command sets `TAGMEMORAG_RUN_BROWSER_UI=1` internally.
- [ ] Unit tests cover parser wiring and pass/fail/error return behavior without launching a real browser.
- [ ] README documents both local backend readiness and browser QA readiness.
- [ ] Focused static/unit checks pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
