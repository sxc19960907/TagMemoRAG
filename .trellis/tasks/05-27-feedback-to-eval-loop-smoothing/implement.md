# Feedback To Eval Loop Smoothing Implementation Plan

## Checklist

- [x] Start the child task.
- [x] Read Trellis frontend/backend quality guidance.
- [x] Add Q&A feedback review link rendering.
- [x] Add Retrieval Quality `feedback_id` URL auto-selection.
- [x] Update unit/static tests for both JS assets.
- [x] Update browser flow to follow the feedback review link.
- [x] Mark parent task child 4 and child 5 progress accurately.
- [x] Run focused static, unit, and browser checks.
- [x] Commit and archive the child task.

## Validation Commands

```bash
node --check src/tagmemorag/web/static/qa_page.js
node --check src/tagmemorag/web/static/retrieval_quality.js
python3 -m py_compile tests/unit/test_manual_library_ui.py tests/integration/test_browser_admin_ui.py
uv run pytest tests/unit/test_manual_library_ui.py -q
uv run python -m tagmemorag readiness browser-qa
```

## Risk Points

- Feedback notes currently use textContent; rendering a link must still escape all dynamic values.
- Retrieval Quality list pagination is limit-based. If a future deployment has more than 50 new rows, a direct feedback id may not be in the default loaded set; this task should handle that gracefully without changing backend filters.
