# design.md - M19 Search Diagnostics / Operator Debug Metadata

## Scope

M19 adds an opt-in diagnostic response surface for search execution. It should make API and CLI search behavior explainable to operators while preserving default response compatibility and existing search semantics.

## Current Flow

```text
API /search
  -> compute cache key
  -> return cached payload when present
  -> embed query
  -> execute_search(...)
       -> exact local search OR Qdrant ANN candidate preselection
       -> local WAVE-RAG ranking
       -> SearchExecution(strategy, ann_candidate_count, ann_fallback_reason)
  -> log/tracing strategy details
  -> return normal response without diagnostics
```

```text
CLI search
  -> load config / KB / embedder
  -> execute_search(...)
  -> print {build_id, results}
```

## Proposed Contract

### Config

Add to `SearchConfig`:

```python
debug_metadata_enabled: bool = False
```

Environment override should work through the existing nested settings convention:

```text
TAGMEMORAG__SEARCH__DEBUG_METADATA_ENABLED=true
```

### API Request

Add to `SearchRequest`:

```python
debug: bool | None = None
```

Effective mode:

```python
debug_enabled = bool(request.debug) or settings.search.debug_metadata_enabled
```

Using `None` keeps request compatibility clear: omitted means "use config default"; explicit `true` opts in. Explicit `false` may either mean "off unless config enables globally" or "force off"; MVP should use the simpler rule above unless implementation finds a strong need for force-off semantics.

### Response Shape

When debug mode is disabled, keep the existing payload shape.

When enabled, add:

```json
{
  "debug": {
    "search_strategy": "ann_preselect_then_wave",
    "ann_enabled": true,
    "ann_candidate_count": 2,
    "ann_fallback_reason": "",
    "source_k": 3,
    "steps": 3,
    "aggregate": "max",
    "eligible_node_count": 2
  }
}
```

Field rules:

- `search_strategy`: from `SearchExecution.strategy`.
- `ann_enabled`: effective runtime intent, preferably true only when config and vector provider allow ANN.
- `ann_candidate_count`: from `SearchExecution`.
- `ann_fallback_reason`: from `SearchExecution`; empty string when not applicable.
- `source_k`, `steps`, `aggregate`: from effective search params.
- `eligible_node_count`: `len(SearchExecution.eligible_node_ids)`.

Do not include:

- raw query text
- query vectors
- document chunks
- full result text beyond existing result payloads
- absolute paths
- API keys or secrets
- trace ids/search ids inside `debug`
- candidate ids or scores

### Shared Helper

Add narrow helpers in `api.py` or a shared module only if the CLI needs them:

```python
def search_debug_enabled(request_debug: bool | None, settings: Settings) -> bool:
    ...

def search_debug_payload(execution: SearchExecution, params: Mapping[str, object], *, ann_enabled: bool) -> dict[str, object]:
    ...
```

If both API and CLI need the same payload builder, prefer putting it in `search_runtime.py` to avoid duplicating response-shaping logic. Keep FastAPI/Pydantic imports out of `search_runtime.py`.

## Cache Design

MVP recommendation: include effective debug mode in both cache key and search id.

```text
cache-key parts += ["debug:0" | "debug:1"]
search-id parts += ["debug:0" | "debug:1"]
```

This keeps debug and non-debug payloads from crossing while preserving cache hit behavior for repeated debug requests.

Implementation notes:

- `_compute_cache_key(request, state)` can derive debug mode from request plus global settings.
- `_compute_search_id(request, state, trace_id)` should include the same effective debug mode.
- When caching a debug response, store the `debug` object with the cached payload.
- Existing cache-hit rehydration can continue to add `trace_id`, `search_id`, `search_time_ms`, and `cache`.

Alternative considered: bypass cache for debug requests. This is simpler but less representative for operators investigating cache behavior, so it is not preferred unless implementation friction is high.

## API Data Flow

```text
SearchRequest(debug)
  -> effective_debug = request.debug or settings.search.debug_metadata_enabled
  -> cache key includes effective_debug
  -> cache hit:
       cached payload already matches debug shape
  -> cache miss:
       execute_search(...)
       payload = normal response
       if effective_debug:
           payload["debug"] = search_debug_payload(...)
       cache payload shape under debug-specific key
```

## CLI Data Flow

```text
tagmemorag search QUESTION [--debug-search]
  -> execute_search(...)
  -> payload = {"build_id": ..., "results": ...}
  -> if args.debug_search or cfg.search.debug_metadata_enabled:
       payload["debug"] = search_debug_payload(...)
  -> print JSON
```

CLI can include `kb_name` in debug mode only if useful, but should not change default output unless the task deliberately chooses to align CLI with API more broadly.

## Observability

Existing logs/tracing already include search strategy and ANN fields on cache miss. M19 should avoid adding new metrics labels unless there is a concrete need. If additional logs are touched, keep them low-cardinality and avoid raw queries or ids.

## Compatibility

- Existing requests that omit `debug` continue to parse.
- Existing responses remain unchanged unless debug is enabled.
- Existing configs continue to load because the new field has a default.
- Cache entries created before M19 simply use old keys and can expire naturally; no migration is needed.
- NPZ behavior remains exact local search with debug strategy `exact_local`.

## Test Design

Recommended tests:

1. API default response omits `debug`.
2. API `debug=true` response includes debug fields for exact local search.
3. API config-enabled debug returns debug fields when request omits `debug`.
4. API Qdrant ANN success returns `search_strategy=ann_preselect_then_wave`.
5. API Qdrant ANN failure returns `search_strategy=exact_local` and `ann_fallback_reason=ann_query_failed`.
6. Cache test: non-debug hit omits debug; debug hit includes debug; cache keys are distinct.
7. CLI default output omits debug.
8. CLI `--debug-search` output includes debug.
9. Env/config test for `TAGMEMORAG__SEARCH__DEBUG_METADATA_ENABLED=true`.

## Rollout / Rollback

- Rollout is low risk because the response change is opt-in and config-default-off.
- Rollback can remove the request flag/CLI flag from active use or keep the config false.
- No data migration is required.

## Open Questions

- Should explicit API `debug=false` override global config? MVP recommendation: no; global config is an operator policy.
- Should the debug object include `top_k` and `amplitude_cutoff`? MVP recommendation: include only params operators routinely tune; add more only if tests or docs show value.
- Should cache hits include a field like `debug.cache_key_mode`? MVP recommendation: no; top-level `cache` already reports hit/miss.
