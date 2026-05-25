# LangChain Unified Ingestion Path — Execution Plan

## 0. Guardrails

- Native parser remains default.
- LangChain provider is explicit opt-in.
- Do not refresh eval baselines.
- Do not leak raw text or absolute source paths in diagnostics.

## 1. Implementation Steps

### Step 1 — Config and Signature

- [x] Add parser provider config with validation.
- [x] Include provider in parser signature / incremental compatibility.
- [x] Add config tests for default and env override.

### Step 2 — Unified Parser Helper

- [x] Add helper for effective supported suffixes.
- [x] Add helper for parsing with the selected provider.
- [x] Preserve OCR summary behavior for native PDFs.

### Step 3 — Rebuild Path Wiring

- [x] Update full rebuild source discovery.
- [x] Update dirty chunk estimation / incremental rebuild parsing.
- [x] Update shadow build source discovery/parsing if applicable.
- [x] Update manual library suffix validation to use effective suffixes
  where config is available.

### Step 4 — Tests

- [x] Add HTML fixture ingestion test with LangChain provider.
- [x] Add missing-extra failure test.
- [x] Add default/native preservation tests.
- [x] Extend chunk identity tests for provider changes.

### Step 5 — Eval and Smoke

- [x] Run native parser/chunk identity tests.
- [x] Run adapter tests with `--extra langchain`.
- [x] Run coffee and product manual eval gates in default/native mode.
- [x] Run an HTML build/search smoke with LangChain provider.

## 2. Validation Commands

```bash
uv run pytest tests/unit/test_config_env.py tests/unit/test_parser.py tests/unit/test_chunk_identity.py
uv run --extra langchain pytest tests/unit/test_langchain_adapter.py
uv run --extra langchain pytest tests/unit/test_langchain_ingestion.py
uv run python -m tagmemorag.cli eval run --config examples/config/local-hashing-npz.yaml --suite tests/fixtures/eval/coffee.jsonl --docs tests/fixtures --eval-data-dir .tmp/eval-langchain-ingest-coffee --min-recall-at-k 0.738095 --min-mrr 0.928571 --min-hit-at-k 1.0
uv run python -m tagmemorag.cli eval run --config examples/config/local-hashing-npz.yaml --suite tests/fixtures/eval/product_manuals.jsonl --docs tests/fixtures/product_manuals --eval-data-dir .tmp/eval-langchain-ingest-product --min-recall-at-k 0.8 --min-mrr 0.75 --min-hit-at-k 0.8
git diff --check
```

## 2.1 Validation Results

- `uv run --extra langchain pytest tests/unit/test_langchain_ingestion.py tests/unit/test_config_env.py tests/unit/test_chunk_identity.py tests/unit/test_langchain_adapter.py tests/unit/test_manual_library.py::test_safe_source_path_rejects_traversal_and_unsupported_suffix tests/unit/test_manual_library.py::test_safe_source_path_allows_html_when_langchain_provider_enabled tests/unit/test_storage_state.py::test_build_save_load_kb`
  passed: 58 tests.
- `coffee.jsonl` native/default eval passed: recall 0.785714, mrr 0.928571,
  hit@k 1.0.
- `product_manuals.jsonl` native/default eval passed: recall 1.0, mrr 1.0,
  hit@k 1.0.
- `git diff --check` passed.

## 3. Exit Criteria

- [x] Default provider behavior unchanged.
- [x] LangChain provider indexes HTML fixture.
- [x] Missing optional dependency fails clearly.
- [x] Provider changes parser signature.
- [x] Native eval gates pass.
- [ ] Work is committed and task archived.
