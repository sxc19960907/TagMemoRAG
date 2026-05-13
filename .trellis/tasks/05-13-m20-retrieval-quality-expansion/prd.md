# M20 Retrieval Quality Expansion

## Goal

Expand TagMemoRAG's retrieval evaluation coverage so future ranking, metadata, tag, rebuild, and ANN changes can be judged against realistic product-manual behavior instead of only the current coffee-machine smoke suite.

M20 is measurement-first: it should improve the eval corpus, runner fidelity, and regression checks without tuning ranking constants unless a basic correctness regression blocks the new evals.

## Background / Known Context

- M19 added opt-in search diagnostics so operators and tests can see exact-local, ANN-assisted, and ANN-fallback behavior.
- Current eval fixtures are centered on `tests/fixtures/coffee_machine.md` and `tests/fixtures/eval/coffee.jsonl`.
- `tagmemorag eval run` already produces a JSON report with suite summary, per-case metrics, expected matchers, actual top-k results, and failures.
- Existing eval cases support `source_file`, `header`, `anchor_key`, `text_contains`, `metadata`, tags, per-case `top_k_override`, and per-case thresholds.
- Existing `run_eval()` builds or loads KB state, then calls `wave_search()` directly. That means current evals do not exercise `execute_search()`, Qdrant ANN preselection, ANN fallback, tag-governed filters, or M19 search diagnostics.
- Default tests must remain deterministic, small, offline, and free of live Qdrant/network requirements.
- Project safety guidance forbids raw secrets, vectors, machine-specific absolute paths, and high-cardinality operational identifiers in reports, logs, metrics, and operator metadata. Eval fixtures may contain short synthetic manual text because they are test data.

## Requirements

### 1. Expanded Product-Manual Fixture Corpus

- Add deterministic synthetic manuals beyond the coffee machine fixture, covering at least:
  - refrigerator temperature/noise
  - washer error codes and maintenance
  - air-conditioner modes and filter cleaning
  - dishwasher cleaning and fault recovery
- Keep fixtures small enough for default local test execution with the hashing embedder.
- Use relative fixture paths and synthetic content only.
- Include metadata sidecars where needed to test manual/category/model/language/tag behavior.

### 2. Expanded Eval Suite

- Add a new broader eval suite, for example `tests/fixtures/eval/product_manuals.jsonl`.
- Include Chinese and English query variants where useful.
- Cover realistic retrieval scenarios:
  - semantic lookup by symptom or task
  - error/fault-code lookup
  - metadata relevance, including manual id/category/model/language where useful
  - tag relevance and tag synonym/governance behavior if the existing runner can support it cleanly
  - anchor-boosted result expectations
  - ANN enabled versus disabled behavior
  - managed-library incremental rebuild before/after changed manuals
- Keep pass thresholds explicit and realistic for hashing-embedder determinism.

### 3. Eval Runner Fidelity

- Update eval execution so ranking uses the same `execute_search()` path as API/CLI search, rather than bypassing it with direct `wave_search()`.
- Preserve the existing JSON report shape where possible.
- Add optional report fields only when useful and low-risk, such as search strategy/debug summaries, without leaking raw vectors, secrets, absolute paths, or candidate id lists.
- Ensure evals can exercise ANN-assisted search with fake Qdrant clients in tests without requiring a live Qdrant service.

### 4. Regression Coverage

- Add focused tests proving:
  - the expanded suite loads and produces a reproducible report
  - at least one ANN-preselected eval case still returns the expected final WAVE-RAG result
  - at least one managed-library incremental rebuild followed by eval reflects changed manual content
  - default eval/report behavior remains backward compatible for the existing coffee suite
- Default test suite must stay offline and stable.

### 5. Documentation

- Update README or adjacent docs with the expanded eval suite path and example commands.
- Document when to use the smoke coffee suite versus the broader M20 suite.
- Note that M20 is for measurement, not ranking tuning.

## Acceptance Criteria

- [ ] A deterministic multi-category product-manual fixture corpus exists.
- [ ] A broader eval JSONL suite covers semantic lookup, metadata/tag relevance, anchor influence, ANN behavior, and incremental rebuild behavior.
- [ ] `run_eval()` uses `execute_search()` or an equivalent shared search execution path so eval behavior matches API/CLI ranking semantics.
- [ ] Existing coffee eval CLI test still passes.
- [ ] A new eval test proves ANN preselection does not remove an expected final WAVE-RAG result.
- [ ] A new eval or integration test covers managed-library incremental rebuild followed by eval.
- [ ] Eval reports remain reproducible and do not require network access or live Qdrant.
- [ ] Reports/config snapshots do not include raw secrets, vectors, machine-specific absolute paths beyond caller-provided fixture paths, or candidate id lists.
- [ ] README/docs explain the expanded suite and commands.
- [ ] `uv run pytest tests/ -q` passes.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- Expanded fixtures and eval suite are committed.
- Eval runner fidelity gaps are closed or explicitly documented with follow-up tasks.
- Tests cover expanded suite loading/reporting, ANN, and incremental rebuild eval behavior.
- Documentation gives operators/developers a repeatable command.
- No ranking constants are tuned unless required to preserve basic correctness and backed by report evidence.

## Out of Scope

- Changing WAVE-RAG ranking semantics as the main goal.
- Making Qdrant remote ranking authoritative.
- Adding live Qdrant integration tests to the default suite.
- Creating a large benchmark corpus or downloading external datasets.
- Building a UI for eval browsing.
- Adding production telemetry or dashboards.

## Research References

- `.trellis/workspace/suixingchen/roadmap.md`
- `.trellis/tasks/05-13-m20-retrieval-quality-expansion/research/code-context.md`
- `src/tagmemorag/eval/dataset.py`
- `src/tagmemorag/eval/runner.py`
- `src/tagmemorag/search_runtime.py`
- `tests/fixtures/eval/coffee.jsonl`
- `tests/e2e/test_eval_cli.py`
