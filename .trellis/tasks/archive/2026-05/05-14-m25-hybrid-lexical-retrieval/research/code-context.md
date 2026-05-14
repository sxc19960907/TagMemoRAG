# Code Context - M25 Hybrid Lexical Retrieval

Date: 2026-05-14

## Current Search Flow

- `src/tagmemorag/search_runtime.py`
  - `execute_search()` is the main shared boundary for API/CLI/eval search execution.
  - It applies metadata filters with `filter_node_ids()`.
  - If Qdrant ANN is enabled, `_ann_eligible_node_ids()` asks the vector store for candidate node IDs and intersects them with filters.
  - It then calls `wave_search()` with effective `eligible_node_ids`.
  - `search_cache_suffix()` currently accounts for exact-local vs ANN strategy, not lexical behavior.
  - `search_debug_payload()` exposes low-cardinality strategy/ANN/search-parameter fields.

- `src/tagmemorag/wave_searcher.py`
  - `wave_search()` seeds propagation from vector-similarity-ranked `source_k` nodes.
  - Graph propagation supports `aggregate=max` and `aggregate=sum`; M23 rejected `sum` as a default because it regressed product-manual evals.
  - Metadata and tag boosts are additive and bounded after propagation.
  - `filter_node_ids()` and `normalize_filters()` provide reusable filter normalization.
  - `metadata_from_node()` is available through `manuals.py` and should be reused for lexical searchable fields.

- `src/tagmemorag/config.py`
  - `SearchConfig` currently includes vector/WAVE parameters, metadata/tag boosts, ANN settings, and debug enablement.
  - New lexical settings should live here if production ranking changes.

## M23 Evidence

- `research/experiments.md` under M23 recorded exact-local baselines and parameter sweeps.
- Product-manual baseline: `precision_at_k=0.125`, `recall_at_k=1.0`, `mrr=1.0`, `hit_at_k=1.0`.
- Coffee baseline: `precision_at_k=0.214286`, `recall_at_k=0.928571`, `mrr=0.928571`, `hit_at_k=1.0`.
- `source_k=4`, `steps=2`, `decay=0.55`, plus additional probes did not improve aggregate metrics.
- `aggregate=sum` regressed product metrics and should not become default.
- Lexical retrieval was deferred because existing exact-code cases already passed; M25 must add harder cases before changing ranking.

## Likely Files

- `src/tagmemorag/lexical_search.py` (new)
- `src/tagmemorag/search_runtime.py`
- `src/tagmemorag/wave_searcher.py`
- `src/tagmemorag/config.py`
- `src/tagmemorag/api.py` if request/debug/cache behavior changes require model updates
- `src/tagmemorag/cli.py` if request-level lexical overrides are added
- `src/tagmemorag/eval/runner.py` / report config snapshot if new settings need to be captured
- `tests/fixtures/eval/product_manuals.jsonl`
- focused tests under `tests/unit/`
- `README.md`
- `.trellis/spec/backend/` if durable search/debug/cache conventions change

## Constraints

- Final ranking remains local WAVE-RAG.
- Qdrant ANN remains candidate generation only.
- Default test suite remains offline and deterministic.
- No raw query text, tokens, document text, candidate ID lists, vectors, secrets, or high-cardinality paths in debug/logs/metrics.
