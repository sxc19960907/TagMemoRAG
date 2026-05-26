# Browser RAG experience acceptance

## Goal

Verify the current browser-first RAG experience end to end and fix any small blocking issues found on the normal user path.

## Requirements

- Exercise the real browser path for a user who uploads a manual, triggers rebuild, navigates to QA from the UI, asks a question, and sees cited evidence.
- Prefer the existing opt-in Playwright browser smoke coverage instead of inventing a parallel harness.
- If the smoke fails because of a product defect, apply a narrow fix and add or update focused coverage.
- Do not broaden into large UI redesign, ranking changes, provider changes, or deployment work.

## Acceptance Criteria

- [x] The upload/rebuild/QA browser smoke passes locally with `TAGMEMORAG_RUN_BROWSER_UI=1`.
- [x] Any discovered blocker is fixed or explicitly recorded if it is outside this task's scope.
- [x] Focused non-browser checks still pass for touched UI/static code.
- [x] The task records the tested path and outcome for future release confidence.

## Outcome

- Passed the core browser path: upload a manual, trigger rebuild, navigate to QA from Manual Library, ask a question, and receive cited evidence.
- Passed the full opt-in browser UI integration suite covering admin UI, library-to-QA, upload/rebuild/QA, failure states, insufficient evidence, and follow-up context.
- No product blocker was found in this pass, so no production code change was needed.

## Validation

- `TAGMEMORAG_RUN_BROWSER_UI=1 .venv/bin/python -m pytest tests/integration/test_browser_admin_ui.py::test_browser_upload_manual_rebuild_then_qa_user_flow -q -s` → `1 passed`
- `TAGMEMORAG_RUN_BROWSER_UI=1 .venv/bin/python -m pytest tests/integration/test_browser_admin_ui.py -q` → `6 passed`
- `.venv/bin/python -m pytest tests/unit/test_manual_library_ui.py tests/unit/test_answer_api.py tests/unit/test_qa_context.py -q` → `31 passed`
- `node --check` for admin/browser static scripts → passed
- `git diff --check` → passed

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
