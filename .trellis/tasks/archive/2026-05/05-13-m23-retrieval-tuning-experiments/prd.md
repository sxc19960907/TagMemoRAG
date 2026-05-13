# M23 Retrieval Tuning Experiments

## Goal

Use the expanded M20 product-manual eval suite to make evidence-backed retrieval improvements while preserving TagMemoRAG's core ranking contract: Qdrant may generate candidates, but final ranking remains local WAVE-RAG over the loaded graph and vectors.

M23 should turn retrieval tuning from guesswork into a repeatable experiment loop. The task should produce baseline reports, compare constrained tuning variants, adopt only changes that improve or preserve aggregate quality, and document rejected variants so future work does not repeat dead ends.

## Background / Known Context

- M19 added opt-in search diagnostics for exact-local, ANN-assisted, and ANN-fallback behavior.
- M20 added `tests/fixtures/eval/product_manuals.jsonl`, synthetic product-manual fixtures, and eval runner execution through `execute_search()`.
- M21 and M22 improved rebuild and Qdrant operator visibility; M23 should not change those operational contracts.
- Current default search settings are conservative: `top_k=5`, `source_k=3`, `steps=3`, `decay=0.7`, `amplitude_cutoff=0.01`, `aggregate=max`, `metadata_field_boost=0.05`, and `tag_boost=0.03`.
- Eval reports already include per-case metrics, failures, actual top-k results, search strategy, ANN candidate count, and ANN fallback reason.
- The broader M20 suite intentionally uses low thresholds because the hashing embedder is deterministic but not semantically strong.
- Search safety constraints still apply: no raw secrets, vectors, raw external/private manual text, high-cardinality candidate lists, or machine-specific paths in logs, metrics, or operator metadata.

## Requirements

### 1. Baseline And Experiment Evidence

- Create a repeatable way to run baseline retrieval evals for:
  - the coffee smoke suite
  - the M20 product-manual suite
  - exact local search
  - ANN-preselected search where fake-client coverage is available
- Preserve the baseline report or compact summary in the task research directory.
- For every tuning variant considered, record:
  - changed parameters or code behavior
  - eval command used
  - aggregate metrics before/after
  - per-case regressions and wins
  - decision: adopt, reject, or defer
- Do not accept a tuning change based only on subjective result inspection.

### 2. Conservative Search Parameter Tuning

- Evaluate bounded changes to existing search configuration and ranking knobs:
  - `source_k`
  - `steps`
  - `decay`
  - `amplitude_cutoff`
  - `aggregate`
  - `metadata_field_boost`
  - `tag_boost`
  - optional request/config defaults for `top_k` only if report evidence shows a real need
- Favor defaults that improve or preserve aggregate `recall_at_k`, `mrr`, and `hit_at_k` across the product-manual suite.
- Avoid changes that optimize one narrow case while causing unexplained regressions elsewhere.
- If no parameter variant clearly improves the suite, leave defaults unchanged and document the result.

### 3. Metadata-Aware Reranking Exploration

- Explore a small, local-only metadata-aware reranking adjustment only if parameter tuning exposes a recurring category/model/tag mismatch.
- Reuse already-loaded graph node metadata and existing normalized filter/tag helpers.
- Keep any adopted reranking deterministic, additive, bounded, and covered by tests.
- Do not make product metadata required for retrieval; no-sidecar and legacy KB behavior must remain compatible.

### 4. Hybrid Lexical Exploration

- Explore lexical signals only as a constrained experiment if eval evidence shows semantic recall gaps such as exact fault codes, product models, or short maintenance terms being missed.
- Prefer lightweight standard-library token matching or existing parsed text over introducing a new search engine.
- Any adopted lexical feature must:
  - be deterministic and offline
  - avoid storing a new durable index unless explicitly justified
  - preserve WAVE-RAG graph propagation as the final ranking path
  - include tests for Chinese/English or fault-code examples as relevant
- It is acceptable for M23 to defer lexical retrieval with a documented follow-up if scope becomes too large.

### 5. ANN Safety

- Preserve Qdrant ANN as candidate generation only.
- Do not make Qdrant scores authoritative final ranking.
- Do not add payload-filtered ANN by default in M23 unless eval evidence and tests prove no recall regression for filtered searches.
- Any ANN-related tuning should focus on safe knobs such as `ann_candidate_k` and fallback behavior documentation, not remote ranking semantics.

### 6. Tooling And Documentation

- Add or update developer-facing commands for running the tuning suites if existing CLI commands are not enough.
- Update README or adjacent docs with:
  - baseline eval commands
  - how to compare tuning variants
  - accepted defaults, if any changed
  - known limitations and rejected approaches
- Keep reports and docs concise enough to be useful during future regressions.

## Acceptance Criteria

- [ ] A baseline retrieval report or compact summary for coffee and product-manual suites is captured under this task.
- [ ] At least three bounded tuning variants are evaluated and documented, even if all are rejected.
- [ ] Any adopted default or ranking behavior change links to eval evidence and has focused tests.
- [ ] Aggregate product-manual `recall_at_k`, `mrr`, and `hit_at_k` improve or remain equal versus baseline; any per-case regression is explicitly justified.
- [ ] Coffee smoke eval remains passing.
- [ ] ANN-preselection behavior remains candidate-generation-only and final ranking remains local WAVE-RAG.
- [ ] Existing Qdrant, rebuild, cache, API, CLI, and eval tests continue to pass.
- [ ] No default test requires live Qdrant or network access.
- [ ] Documentation explains how to reproduce the baseline and compare future tuning changes.
- [ ] `uv run pytest tests/ -q` passes before final handoff.

## Definition Of Done

- PRD, design, and implementation checklist are complete.
- Baseline and experiment findings are written to `research/`.
- Adopted changes, if any, are implemented with proportional tests and README updates.
- Rejected or deferred tuning ideas are documented with reasons.
- Full test suite passes.

## Out Of Scope

- Replacing WAVE-RAG with a different ranking engine.
- Making Qdrant or any remote ANN score the final authoritative ranker.
- Adding a live Qdrant integration test to default CI.
- Downloading external benchmark datasets.
- Large-scale LLM reranking or online learning.
- Adding a database, search daemon, background experiment scheduler, or eval dashboard.
- Optimizing for production latency before quality deltas are understood.

## Research References

- `.trellis/workspace/suixingchen/roadmap.md`
- `.trellis/tasks/archive/2026-05/05-13-m19-search-diagnostics-operator-debug-metadata/prd.md`
- `.trellis/tasks/archive/2026-05/05-13-m20-retrieval-quality-expansion/prd.md`
- `.trellis/tasks/archive/2026-05/05-13-m20-retrieval-quality-expansion/design.md`
- `.trellis/tasks/archive/2026-05/05-13-m22-qdrant-operations-documentation-inspection-tools/prd.md`
- `.trellis/tasks/05-13-m23-retrieval-tuning-experiments/research/code-context.md`
- `src/tagmemorag/search_runtime.py`
- `src/tagmemorag/wave_searcher.py`
- `src/tagmemorag/eval/runner.py`
- `tests/fixtures/eval/product_manuals.jsonl`
