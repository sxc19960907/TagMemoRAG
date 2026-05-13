# M19 Code Context

## Relevant Modules

- `src/tagmemorag/search_runtime.py`
  - `SearchExecution` already exposes `strategy`, `ann_candidate_count`, `ann_fallback_reason`, and `eligible_node_ids`.
  - `execute_search()` decides between exact local search and Qdrant ANN candidate preselection, then always calls local `wave_search()`.
  - `search_cache_suffix()` already separates ANN-related cache modes.

- `src/tagmemorag/api.py`
  - `SearchRequest` is the API request model to extend with `debug`.
  - `_search_impl()` computes cache status, embeds the query, calls `execute_search()`, logs strategy fields, and shapes the response.
  - `_compute_cache_key()` and `_compute_search_id()` should include effective debug mode to prevent response-shape cross-contamination.
  - Cache-hit responses merge cached payload fields with new `trace_id`, `search_id`, `search_time_ms`, and `cache`.

- `src/tagmemorag/cli.py`
  - `search` command currently accepts question, KB, top-k, config, and metadata filters.
  - It calls `execute_search()` directly and prints `{build_id, results}`.
  - `--debug-search` can reuse the same debug payload builder as API.

- `src/tagmemorag/config.py`
  - `SearchConfig` is the home for `debug_metadata_enabled`.
  - Existing settings support nested env overrides with `TAGMEMORAG__SEARCH__...`.

## Existing Tests To Update

- `tests/unit/test_api.py`
  - ANN success/fallback tests already use `FakeQdrantClient`.
  - Add debug response assertions here.

- `tests/unit/test_cli.py`
  - CLI search tests already cover filters and Qdrant ANN.
  - Add `--debug-search` output assertions.

- `tests/unit/test_cache.py`
  - Cache key tests should account for debug mode.

- `tests/unit/test_config_env.py`
  - Add env override coverage for `TAGMEMORAG__SEARCH__DEBUG_METADATA_ENABLED=true`.

## Safety Notes

- Do not add raw query text to debug payload. The query is already supplied by the caller; repeating it in diagnostics creates unnecessary cache/logging risk.
- Do not add candidate ids or scores. They are high-cardinality and can expose graph internals.
- Do not add vectors or raw chunk text.
- Keep metrics labels unchanged unless a later observability task has a clear need.
