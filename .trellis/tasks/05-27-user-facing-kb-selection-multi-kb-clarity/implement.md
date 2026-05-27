# User Facing KB Selection And Multi KB Clarity Implementation Plan

## Checklist

- [x] Start the child task.
- [x] Read Trellis frontend/backend quality guidance.
- [x] Update QA template with active KB selector markup.
- [x] Update QA JS to load KBs, populate selector, and navigate on change.
- [x] Add CSS for compact KB selection controls.
- [x] Add i18n strings.
- [x] Update unit tests for QA shell/static asset.
- [x] Update focused browser QA flow assertions.
- [x] Run static, unit, and browser QA readiness checks.
- [ ] Commit and archive the child task.

## Validation Commands

```bash
node --check src/tagmemorag/web/static/qa_page.js
python3 -m py_compile tests/unit/test_manual_library_ui.py tests/integration/test_browser_admin_ui.py
uv run pytest tests/unit/test_manual_library_ui.py -q
uv run python -m tagmemorag readiness browser-qa
```

## Risk Points

- The page language switcher currently mounts inside `.qa-left-rail`; new markup should translate correctly.
- Preserve prefilled questions from eval report links when switching KBs.
- Avoid hidden conversation-history reuse across KBs by reloading the page on selection change.
