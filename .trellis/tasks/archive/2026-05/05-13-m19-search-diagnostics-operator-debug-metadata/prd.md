# M19 Search Diagnostics / Operator Debug Metadata

## Goal

Expose controlled search diagnostics so operators can understand whether a request used exact local search, Qdrant ANN preselection, or an ANN fallback path, without changing default response noise or leaking sensitive data.

## Background / Known Context

- M16 added Qdrant ANN preselection as candidate generation only; final ranking remains local WAVE-RAG.
- M17 added regression coverage proving ANN-assisted search after incremental rebuild still respects current graph node ids.
- `search_runtime.SearchExecution` already carries `strategy`, `ann_candidate_count`, and `ann_fallback_reason`.
- API search logs and tracing already record search strategy and ANN candidate/fallback details on cache misses.
- API and CLI response bodies currently do not expose these diagnostics.
- `_compute_cache_key()` and `_compute_search_id()` currently include search parameters, filters, build id, anchors version, and ANN strategy suffix, but they do not include any debug/diagnostic mode flag.
- Cache-hit API responses are rebuilt from cached payloads plus new `trace_id`, `search_id`, `search_time_ms`, and `cache`.
- Existing observability guidance forbids raw query text, document text, vectors, secrets, and high-cardinality values in logs, metrics, tracing, and operator metadata.

## Requirements

### 1. Explicit Debug Opt-In

- Default API and CLI search responses must remain backward compatible.
- Add a config switch such as `search.debug_metadata_enabled=false`.
- Add a per-request API opt-in, likely `debug=true` on `SearchRequest`.
- Add a CLI opt-in, likely `tagmemorag search --debug-search`.
- Debug metadata should be returned when either:
  - config enables it globally, or
  - the request/CLI explicitly opts in.

### 2. Diagnostic Payload Shape

- Add low-cardinality diagnostic metadata under one additive object, recommended key: `debug`.
- Include only operationally useful fields such as:
  - `search_strategy`: `exact_local` or `ann_preselect_then_wave`
  - `ann_enabled`: boolean config/runtime intent
  - `ann_candidate_count`: integer
  - `ann_fallback_reason`: low-cardinality string, empty when no fallback
  - `source_k`
  - `steps`
  - `aggregate`
  - `eligible_node_count`
- Do not include raw query text, vectors, raw chunk text, absolute source paths, secrets, trace ids, search ids, or full candidate id lists.
- Preserve existing top-level response fields: `build_id`, `kb_name`, `trace_id`, `search_id`, `results`, `search_time_ms`, and `cache`.

### 3. Cache Semantics

- Debug and non-debug requests must not accidentally share a cached body with different response shape.
- Choose one of these safe approaches:
  - include debug mode in the cache key and cache debug payloads separately, or
  - bypass cache for debug requests.
- Preferred MVP: include debug mode in the cache key, so debug requests can still show `cache=hit` with matching debug metadata.
- Search ids should also include the effective debug mode so a debug and non-debug response for the same query are distinguishable.

### 4. API Behavior

- Add `debug: bool | None = None` to `SearchRequest`.
- Use one helper to compute effective debug mode from request plus config.
- On cache miss, build debug metadata from `SearchExecution` and search params.
- On cache hit, return cached debug metadata only when the cache key was created for debug mode.
- Keep structured logs and tracing low-cardinality.

### 5. CLI Behavior

- Add `--debug-search` to the `search` command.
- When enabled, include the same `debug` object in the printed JSON.
- Keep existing CLI output unchanged when the flag is absent and config debug is false.

### 6. Compatibility

- Existing API clients must not need to change.
- Existing config files must load without new required fields.
- Existing cache tests may need expected-key updates only for the additive debug-mode suffix.
- No new production dependency should be added.
- Default tests must not require live Qdrant or network access.

## Acceptance Criteria

- [ ] Default API `/search` response does not include `debug`.
- [ ] API `/search` with `debug=true` includes a `debug` object with strategy, ANN candidate/fallback details, and effective search params.
- [ ] Config-level `search.debug_metadata_enabled=true` includes `debug` without a per-request flag.
- [ ] CLI `search` output remains unchanged by default.
- [ ] CLI `search --debug-search` includes the same `debug` object shape as API.
- [ ] ANN-enabled Qdrant search reports `ann_preselect_then_wave` and candidate count when ANN succeeds.
- [ ] ANN fallback reports `exact_local` plus a low-cardinality `ann_fallback_reason`.
- [ ] Cache tests prove debug and non-debug response shapes do not cross-contaminate.
- [ ] Diagnostics do not include raw query text, vectors, document text, absolute source paths, trace ids, search ids, or candidate id lists.
- [ ] Existing API, CLI, cache, observability, and Qdrant ANN tests pass.
- [ ] `uv run pytest tests/ -q` passes.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- API and CLI debug metadata are implemented behind explicit opt-in/config.
- Tests cover default, debug, ANN success, ANN fallback, and cache behavior.
- No metrics labels or logs gain high-cardinality or sensitive fields.
- README/config documentation is updated if the new config option or CLI flag is operator-facing.

## Out of Scope

- Changing WAVE-RAG ranking semantics.
- Making Qdrant remote ranking authoritative.
- Returning raw ANN candidate ids or scores.
- Adding payload-filtered ANN search.
- Adding a live Qdrant integration test to the default suite.
- Building a UI for search diagnostics.
- Expanding eval fixtures; that belongs to M20.

## Research References

- `.trellis/workspace/suixingchen/roadmap.md`
- `.trellis/tasks/archive/2026-05/05-13-m16-qdrant-ann-preselection/design.md`
- `.trellis/tasks/archive/2026-05/05-13-m17-qdrant-incremental-ann-integration-regression/prd.md`
- `.trellis/spec/backend/logging-guidelines.md`
- `src/tagmemorag/search_runtime.py`
- `src/tagmemorag/api.py`
- `src/tagmemorag/cli.py`
