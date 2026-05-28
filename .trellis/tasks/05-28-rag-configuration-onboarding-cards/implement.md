# Implementation Plan

## Checklist

- [x] Add local capability summary helpers in `api_rag_readiness.py`.
- [x] Add unit coverage for capability payloads and missing prerequisites.
- [x] Add capability section to readiness template.
- [x] Render capability cards in `rag_readiness.js`.
- [x] Add scoped CSS for capability cards.
- [x] Add i18n entries for new visible text.
- [x] Extend browser readiness guide coverage.
- [x] Run focused unit and browser tests.
- [x] Run broader non-performance gate.
- [x] Commit, archive, and record journal.

## Validation Commands

```bash
uv run pytest tests/unit/test_manual_library_ui.py::test_rag_readiness_summary_reports_configuration_capabilities tests/unit/test_manual_library_ui.py::test_rag_readiness_summary_reports_missing_live_answer_env -q
TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_rag_readiness_onboarding_guide -q
uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py
```

## Risk Notes

- Avoid introducing remote calls into readiness page load.
- Keep new payload additive and safe.
- Do not let optional disabled features make the whole KB `not_ready`.
