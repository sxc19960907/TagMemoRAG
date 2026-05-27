# RAG User Experience Completion Program Implementation Plan

## Ordered Work

- [x] Create and complete child task 1: first-run/demo experience stabilization.
- [x] Create and complete child task 2: browser-first QA readiness quality gate.
- [x] Create and complete child task 3: test tier and quality-gate documentation.
- [x] Create and complete child task 4: user-facing KB selection and multi-KB clarity.
- [x] Create and complete child task 5: feedback-to-eval loop smoothing.
- [x] Create and complete child task 6: deployment/pilot readiness pass.
- [ ] Create and complete child task 7: integrated black-box user acceptance review.

## Validation Pattern

Each child task should define exact commands, but the recurring baseline is:

```bash
node --check src/tagmemorag/web/static/qa_page.js
uv run pytest tests/unit/test_manual_library_ui.py tests/unit/test_answer_api.py -q
TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_manual_library_to_qa_user_flow -q
```

## Review Gates

- Do not start a child before its `prd.md` is testable.
- Add `design.md` and `implement.md` for any child that touches multiple layers.
- Run `trellis-before-dev` before editing code in a child task.
- Run `trellis-check` before finishing each child task.
- Archive completed child tasks and record progress in the journal.

## Network

Do not push to GitHub until the user says the network has recovered or explicitly asks to retry.
