# Implementation Plan

## Checklist

- [x] Review answer prompt/generator/API flow and existing browser QA helpers.
- [x] Add citation-gating behavior after model generation so successful answers require valid citations when evidence citations are available.
- [x] Add unit coverage for uncited OpenAI-compatible generations.
- [x] Add opt-in real LLM browser acceptance config/helper/test.
- [x] Run focused answer tests.
- [x] Run focused browser tests with default skip/offline mode.
- [x] If credentials are present, run the real LLM browser acceptance test.
- [x] Run a broader non-performance gate before archive.

## Validation Commands

```bash
uv run pytest tests/unit/test_answer_generator.py -q
TAGMEMORAG_RUN_BROWSER_UI=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_real_product_pdf_source_preview_user_flow tests/integration/test_browser_admin_ui.py::test_browser_qa_insufficient_evidence_refusal -q
TAGMEMORAG_RUN_BROWSER_UI=1 TAGMEMORAG_RUN_REAL_LLM_QA=1 uv run pytest tests/integration/test_browser_admin_ui.py::test_browser_real_llm_qa_provider_acceptance -q
uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py
```

## Risk Notes

- Real model tests can be non-deterministic. Assertions should focus on grounding surface and absence of obvious fabrication, not exact wording.
- Do not expose raw prompts, source snippets beyond existing UI, or API keys in failure output.
- Keep all generated runtime data under pytest temp dirs or `.tmp/`, which is gitignored.
