# First Run Demo Experience Stabilization Implementation Plan

## Checklist

- [x] Start the child task with `task.py start`.
- [x] Load backend/web Trellis guidelines before editing.
- [x] Update `src/tagmemorag/demo.py` demo metadata, manual text, and default question.
- [x] Update `src/tagmemorag/cli_parser.py` default library QA question.
- [x] Update browser integration expectations for the library QA user flow.
- [x] Add or update focused unit coverage for demo defaults if an existing test file fits.
- [x] Run static, unit, and affected browser checks.
- [ ] Commit and archive the child task.

## Validation Commands

```bash
python3 -m py_compile src/tagmemorag/demo.py src/tagmemorag/cli_parser.py tests/integration/test_browser_admin_ui.py
node --check src/tagmemorag/web/static/qa_page.js
uv run pytest tests/unit/test_manual_library_ui.py tests/unit/test_answer_api.py -q
TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_manual_library_to_qa_user_flow -q
```

## Risk Points

- Chunk count assertions in browser tests can shift when demo text changes.
- Hashing retrieval may rank short sections differently, so tests should assert useful content without overfitting to exact answer text beyond the key manual passage.
