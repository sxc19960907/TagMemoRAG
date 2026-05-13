# implement.md - M18 Qdrant Payload Maintenance / Batch Refresh

## Implementation Checklist

- [ ] Read backend specs with `trellis-before-dev` before coding.
- [ ] Inspect the installed qdrant-client API for safe batch per-point payload update support.
- [ ] Review current `QdrantVectorStore.update_payloads()` and M15/M17 Qdrant incremental tests.
- [ ] Extend fake Qdrant client support to simulate batch payload refresh and per-point fallback.
- [ ] Implement batch-first payload refresh inside `QdrantVectorStore.update_payloads()`.
- [ ] Preserve per-point fallback for clients without safe batch support.
- [ ] Preserve safe payload filtering for both batch and fallback paths.
- [ ] Add focused storage tests for batch refresh, fallback refresh, and unsafe payload stripping.
- [ ] Add or update managed-library regression coverage with multiple reused points.
- [ ] Add failure coverage proving payload refresh failure blocks stale deletes and graph swap.
- [ ] Decide whether additive payload refresh reporting is useful; add it only if it stays low-cardinality and compatible.
- [ ] Update README/spec only if behavior or operator expectations change.

## Validation

Focused tests:

```bash
uv run pytest tests/unit/test_storage_state.py tests/unit/test_manual_library.py -q
```

If API/CLI-visible rebuild metadata changes:

```bash
uv run pytest tests/unit/test_api.py tests/unit/test_cli.py -q
```

Final check:

```bash
uv run pytest tests/ -q
```

## Review Gates

- Confirm no live Qdrant dependency was introduced into the default suite.
- Confirm batch refresh applies distinct safe payloads per point.
- Confirm reused vectors are not rewritten.
- Confirm reused payload-only refreshes still count as `points_reused`, not `points_upserted`.
- Confirm stale deletes happen only after changed/new upserts and reused payload refreshes succeed.
- Confirm payload refresh failure preserves old served graph and dirty pending state.
- Confirm no raw chunk text, vectors, secrets, raw query text, or unsafe payload fields are stored or logged.

## Rollback Points

- If qdrant-client batch APIs are unavailable or awkward across versions, keep the current per-point implementation and add explicit tests documenting the fallback.
- If reporting fields cause response churn, defer additive metadata and keep optimization observable only in storage tests.
- If one huge batch has unclear memory/transport behavior, chunk batch operations internally while still reducing calls versus one call per point.
