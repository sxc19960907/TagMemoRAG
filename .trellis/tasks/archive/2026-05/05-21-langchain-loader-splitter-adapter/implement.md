# LangChain Loader and Splitter Adapter Spike — Execution Plan

## 0. Guardrails

- Keep LangChain optional; do not add it to base dependencies.
- Do not route production rebuilds through LangChain by default.
- Keep comparison output sanitized: counts, hashes, and metadata key coverage
  only.
- Preserve native parser tests and chunk identity behavior.

## 1. Implementation Checklist

### Step 1 — Inspect Native Parser Fixtures

- [x] Identify existing parser tests that cover Markdown, TXT, PDF, lineage, and
  OCR summary boundaries.
- [x] Pick or add small fixtures that are safe for adapter comparison.

### Step 2 — Add Optional Dependency Boundary

- [x] Add a `langchain` optional dependency extra.
- [x] Create an adapter package that imports LangChain lazily.
- [x] Add a clear unavailable path for environments without the extra.

### Step 3 — Implement Adapter Conversion

- [x] Load source documents with LangChain loaders where available.
- [x] Split loaded documents with a LangChain splitter configured from existing
  parser max/min/overlap settings where the mapping is reasonable.
- [x] Convert adapter output to TagMemoRAG `Chunk` objects with deterministic
  source metadata and adapter-specific lineage metadata.

### Step 4 — Add Safe Comparison Report

- [x] Compare native and adapter chunking for selected fixtures.
- [x] Report chunk counts, length statistics, metadata coverage, and text hashes.
- [x] Avoid raw source text, raw snippets, full source paths, vectors, or secrets.

### Step 5 — Tests

- [x] Unit-test optional import behavior without LangChain.
- [x] Unit-test conversion preserves metadata and deterministic ordering.
- [x] Unit-test comparison report redacts raw text.
- [x] If LangChain is installed in the environment, run adapter fixture comparison
  tests; otherwise they should skip cleanly.

### Step 6 — Eval Gate Notes

- [x] Record that `coffee.jsonl` and `product_manuals.jsonl` must pass before any
  future default parser switch.
- [x] If the adapter shows a promising new loader type, leave it behind an explicit
  opt-in boundary.

## 2. Validation Commands

```bash
uv run pytest tests/unit/test_parser.py
uv run pytest tests/unit/test_chunk_identity.py
uv run pytest tests/unit/test_langchain_adapter.py
uv run --extra langchain python -m tagmemorag.cli langchain compare --file tests/fixtures/coffee_machine.md --root-dir tests/fixtures --min-chars 1
uv run python -m tagmemorag.cli eval run --config examples/config/local-hashing-npz.yaml --suite tests/fixtures/eval/coffee.jsonl --docs tests/fixtures --eval-data-dir .tmp/eval-c1-coffee --min-recall-at-k 0.738095 --min-mrr 0.928571 --min-hit-at-k 1.0
uv run python -m tagmemorag.cli eval run --config examples/config/local-hashing-npz.yaml --suite tests/fixtures/eval/product_manuals.jsonl --docs tests/fixtures/product_manuals --eval-data-dir .tmp/eval-c1-product --min-recall-at-k 0.8 --min-mrr 0.75 --min-hit-at-k 0.8
git diff --check
```

Eval commands may be adjusted to the repository's current CLI arguments if
inspection shows a different accepted form.

## 2.1 Validation Results

- `uv run --extra langchain pytest tests/unit/test_langchain_adapter.py tests/unit/test_parser.py tests/unit/test_chunk_identity.py`
  passed: 29 tests.
- `uv run --extra langchain python -m tagmemorag.cli langchain compare --file tests/fixtures/coffee_machine.md --root-dir tests/fixtures --min-chars 1`
  passed and returned sanitized native vs LangChain chunk stats only.
- `uv run python -m tagmemorag.cli langchain compare --file tests/fixtures/coffee_machine.md --root-dir tests/fixtures`
  returned exit code 2 with a clear optional-extra error when LangChain was not
  requested.
- `coffee.jsonl` passed against the committed hashing baseline-equivalent
  thresholds: recall 0.785714, mrr 0.928571, hit@k 1.0.
- `product_manuals.jsonl` passed: recall 1.0, mrr 1.0, hit@k 1.0.
- A stricter `coffee.jsonl` run with recall/mrr forced to 1.0 failed because
  the current baseline does not target perfect recall; this was not caused by
  the adapter because default rebuild paths remain native.
- `git diff --check` passed.

## 3. Risky Files

- `pyproject.toml`
- `src/tagmemorag/parser.py` if any shared helper is needed
- `src/tagmemorag/chunk_identity.py` if adapter parser signature becomes
  configurable
- new adapter package under `src/tagmemorag/langchain_adapter/`
- parser/adapter tests under `tests/unit/`

## 4. Exit Criteria

- [x] Optional dependency boundary exists.
- [x] Adapter import does not affect default package import.
- [x] Adapter can produce or compare TagMemoRAG chunks on small fixtures.
- [x] Comparison report contains no raw text leakage.
- [x] Native parser and chunk identity tests remain green.
- [x] Eval gates for `coffee.jsonl` and `product_manuals.jsonl` are documented
      for any future default switch.

## 5. Rollback

Delete the adapter package, adapter tests, optional dependency extra, and any
comparison report artifacts. Keep native parser code as the serving path.
