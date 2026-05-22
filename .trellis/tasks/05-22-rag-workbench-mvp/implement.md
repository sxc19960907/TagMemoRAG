# RAG Workbench MVP — Implementation Plan

## Steps

1. Add `/admin/rag-workbench` route in `api.py`.
2. Add `rag_workbench.html` template.
3. Add `rag_workbench.js`:
   - load config;
   - submit `/answer`;
   - render answer, citations, evidence/results, warnings, metadata;
   - update nav links for selected KB.
4. Add small CSS classes to `manual_library.css` only where existing classes do
   not cover the workbench.
5. Add UI route/static tests.
6. Run focused and full validation.

## Validation Commands

```bash
uv run pytest tests/unit/test_manual_library_ui.py tests/unit/test_answer_api.py
git diff --check
uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py
```

If a local browser server is needed for visual verification:

```bash
uv run python -m tagmemorag serve --config examples/config/local-hashing-npz.yaml
```

## Exit Criteria

- [x] `/admin/rag-workbench` serves an HTML shell with KB, token, question, and
      answer/evidence containers.
- [x] `rag_workbench.js` calls `/answer` with `kb_name`, `question`, `top_k`,
      `source_k`, and `include_retrieve=true`.
- [x] The UI renders answer text/refusal/error, citations, warnings, plan id,
      build id, and retrieve evidence/results.
- [x] The UI has links to manual-library and retrieval-quality pages for the
      selected KB.
- [x] Unit tests cover route shell and static JS/CSS references.
- [x] Existing answer API tests remain green.
