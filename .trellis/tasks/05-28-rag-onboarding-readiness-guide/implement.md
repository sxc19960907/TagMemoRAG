# Implementation Plan

## Checklist

- [x] Read readiness API/page/static files and relevant specs.
- [x] Update readiness template structure for onboarding hero, stepper, cards, and recommendations.
- [x] Update readiness JS rendering and safe detail formatting.
- [x] Add readiness-specific CSS polish and responsive behavior.
- [x] Add i18n dictionary entries for new visible text.
- [x] Add or update browser integration coverage for the readiness guide.
- [x] Run focused browser test(s).
- [x] Run focused unit/e2e or broader non-performance gate.
- [ ] Archive task and record journal after commit.

## Validation Commands

```bash
TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_eval_report_viewer tests/integration/test_browser_admin_ui.py::test_browser_manual_library_to_qa_user_flow -q
TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_rag_readiness_onboarding_guide -q
uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py
```

## Risk Notes

- Avoid brittle visual tests that fail on copy-only changes.
- Do not over-expose backend diagnostics while trying to make the page useful.
- Keep new CSS scoped under readiness classes so QA/manual-library layout remains stable.
