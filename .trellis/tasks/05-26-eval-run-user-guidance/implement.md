# Implementation Plan: Eval run user guidance

## Checklist

1. Update `EvalPromotionPreview.to_dict()` summary fields:
   - `suite_path`
   - `report_path`
   - `next_command` with `--reuse-built-kb --output`
   - `command_note`
2. Update Retrieval Quality rendering:
   - display suite path
   - display ready/skipped counts
   - display eval command
   - display command note
3. Update i18n strings and focused CSS if needed.
4. Update tests:
   - feedback unit test asserts summary fields and exported suite parses
   - static UI test asserts rendering hooks
   - browser test asserts command includes `--reuse-built-kb` and `--output`
5. Run validation:
   - `node --check src/tagmemorag/web/static/retrieval_quality.js`
   - `node --check src/tagmemorag/web/static/i18n.js`
   - `uv run pytest tests/unit/test_retrieval_feedback.py tests/unit/test_manual_library_ui.py tests/integration/test_browser_admin_ui.py`
   - focused opt-in browser workflows for Retrieval Quality and Q&A feedback export
   - `git diff --check`

## Risk Points

- Command paths may contain spaces. The generated command should shell-quote paths.
- Export refreshes feedback after success, so browser assertions should wait for stable final UI state.
- Keep JSON summary additions backward-compatible for clients expecting existing fields.
