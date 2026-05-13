# M23 Code Context

## Search Runtime

- `src/tagmemorag/search_runtime.py` owns shared search execution for API, CLI, and eval.
- `execute_search()` filters graph nodes, optionally asks Qdrant for ANN candidates, then calls `wave_search()`.
- `SearchExecution` exposes low-cardinality diagnostics: `strategy`, `ann_candidate_count`, and `ann_fallback_reason`.
- ANN is enabled only when `search.ann_preselect_enabled=true`, `vector_store.provider=qdrant`, and vectors are loaded.
- ANN fallback reasons are low-cardinality strings such as `ann_unavailable`, `ann_query_failed`, `candidate_ids_invalid`, and `filtered_candidates_too_small`.

## WAVE-RAG Ranking

- `src/tagmemorag/wave_searcher.py` owns final local ranking.
- Search parameters include `top_k`, `source_k`, `steps`, `decay`, `amplitude_cutoff`, and `aggregate`.
- Source nodes are chosen by local vector similarity among eligible node ids.
- Waves propagate over graph edges using edge weights and decay.
- `aggregate=max` keeps the strongest wave per node; `aggregate=sum` accumulates wave contributions.
- Metadata/tag boosts currently apply only when explicit filters are present.
- Result ordering is deterministic by final score then node id.

## Config Defaults

- Current defaults live in `src/tagmemorag/config.py` and examples in `config.yaml` / README.
- Search defaults:
  - `top_k=5`
  - `source_k=3`
  - `steps=3`
  - `decay=0.7`
  - `amplitude_cutoff=0.01`
  - `aggregate=max`
  - `metadata_field_boost=0.05`
  - `tag_boost=0.03`
  - `ann_preselect_enabled=false`
  - `ann_candidate_k=64`
  - `ann_force_exact_on_filters=false`

## Eval Runner

- `src/tagmemorag/eval/runner.py` now calls `execute_search()`, so eval follows API/CLI ranking semantics.
- Reports include per-case actual top-k results, matched expectation indexes, failures, and search execution diagnostics.
- M20 product-manual suite lives at `tests/fixtures/eval/product_manuals.jsonl`.
- Product-manual fixtures live under `tests/fixtures/product_manuals/`.
- The e2e eval CLI test already covers product-manual suite execution.

## Existing Regression Coverage

- `tests/unit/test_graph_wave.py` covers anchor boost, propagation, aggregate modes, filters, and metadata/tag boosts.
- `tests/unit/test_eval_runner.py` covers eval report behavior and ANN preselection via fake Qdrant.
- `tests/unit/test_api.py` covers search parameter overrides, debug metadata, ANN success/fallback, filter safety, and anchor inclusion.
- `tests/unit/test_manual_library.py` includes incremental rebuild plus ANN regression coverage.
- `tests/unit/test_storage_state.py` covers Qdrant storage, payloads, collection naming, and M22 inspection.

## Likely M23 Files

- `.trellis/tasks/05-13-m23-retrieval-tuning-experiments/research/experiments.md`
- `src/tagmemorag/config.py` if defaults change
- `config.yaml` and README if defaults/docs change
- `src/tagmemorag/wave_searcher.py` if local ranking behavior changes
- `src/tagmemorag/search_runtime.py` if candidate behavior changes
- `tests/unit/test_graph_wave.py`
- `tests/unit/test_eval_runner.py`
- `tests/unit/test_api.py`
- `tests/e2e/test_eval_cli.py`

## Design Bias

M23 should be conservative. Prefer no default change over a weakly supported change. If the evidence points toward lexical or metadata-aware retrieval, keep the MVP local, deterministic, dependency-light, and easy to revert.
