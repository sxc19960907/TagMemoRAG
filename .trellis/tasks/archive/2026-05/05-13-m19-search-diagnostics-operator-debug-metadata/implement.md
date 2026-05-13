# implement.md - M19 Search Diagnostics / Operator Debug Metadata

## Implementation Checklist

- [x] Read backend specs with `trellis-before-dev` before coding.
- [x] Review `SearchExecution`, API search flow, CLI search flow, and cache key/search id helpers.
- [x] Add `SearchConfig.debug_metadata_enabled: bool = False`.
- [x] Add `debug: bool | None = None` to `SearchRequest`.
- [x] Add a shared debug-mode helper and debug payload builder.
- [x] Include effective debug mode in `_compute_cache_key()`.
- [x] Include effective debug mode in `_compute_search_id()`.
- [x] Add API debug payload on cache misses when effective debug is true.
- [x] Preserve matching debug payload on cache hits through the debug-specific cache key.
- [x] Add `--debug-search` to CLI search.
- [x] Add CLI debug payload when the flag or config enables debug metadata.
- [x] Add or update config/env tests for `search.debug_metadata_enabled`.
- [x] Add API tests for default omitted debug, request-enabled debug, and config-enabled debug.
- [x] Add Qdrant ANN success and ANN fallback debug tests using `FakeQdrantClient`.
- [x] Add cache tests proving debug/non-debug shapes do not cross.
- [x] Add CLI tests for default output and `--debug-search`.
- [x] Update README/config docs if the new flag/config is considered operator-facing.

## Validation

Focused tests:

```bash
uv run pytest tests/unit/test_config_env.py tests/unit/test_cache.py tests/unit/test_api.py tests/unit/test_cli.py -q
```

Qdrant ANN-focused tests:

```bash
uv run pytest tests/unit/test_api.py tests/unit/test_cli.py tests/unit/test_manual_library.py -q
```

Final check:

```bash
uv run pytest tests/ -q
```

## Review Gates

- Confirm default API and CLI search responses remain unchanged.
- Confirm debug response metadata is low-cardinality and safe.
- Confirm cache key/search id behavior separates debug from non-debug responses.
- Confirm Qdrant ANN remains candidate generation only.
- Confirm no raw query text, vectors, raw chunks, source absolute paths, secrets, candidate ids, or trace/search ids are added to `debug`.
- Confirm no live Qdrant service dependency enters the default test suite.

## Rollback Points

- If response schema churn becomes risky, keep only CLI debug for MVP and defer API response metadata.
- If cache integration proves awkward, bypass cache for debug requests instead of caching debug payloads.
- If global config plus per-request behavior is confusing, make explicit request `debug=true` the only MVP trigger and keep config for a later task.
