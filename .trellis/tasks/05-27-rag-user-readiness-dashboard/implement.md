# RAG User Readiness Dashboard Implementation Plan

1. Add `api_rag_readiness.py` with summary helpers, card/action shaping, and status rules.
2. Wire `/admin/rag-readiness` page route and `/admin/rag-readiness/summary` JSON route in `api.py`.
3. Add `rag_readiness.html` and `rag_readiness.js`.
4. Add CSS and i18n strings consistent with existing admin pages.
5. Add navigation links from Workbench, QA, Manual Library, Retrieval Quality, Eval Report, and People admin where appropriate.
6. Add unit tests for the route shell, static asset, summary API, and representative readiness states.
7. Validate with JS syntax checks, py_compile, targeted pytest, browser smoke, and `git diff --check`.

## Validation Commands

```bash
node --check src/tagmemorag/web/static/rag_readiness.js
node --check src/tagmemorag/web/static/i18n.js
python3 -m py_compile src/tagmemorag/api.py src/tagmemorag/api_rag_readiness.py
uv run pytest tests/unit/test_manual_library_ui.py -q
git diff --check
```

## Rollback Points

- If summary logic destabilizes existing diagnostics, remove only `api_rag_readiness.py` route wiring and frontend files; existing pages remain untouched.
- If navigation link churn becomes too wide, keep the dashboard route and add only Workbench/QA links in this task.
