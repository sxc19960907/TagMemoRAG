# implement.md - M17 Qdrant Incremental + ANN Integration Regression

## Implementation Checklist

- [x] Read backend specs with `trellis-before-dev` before coding.
- [x] Review M15 `next-steps.md`, M15 PRD/design, and M16 PRD/design.
- [x] Review current Qdrant fake client support and decide whether it needs extra call tracking.
- [x] Add an integration-style test for Qdrant baseline build -> incremental rebuild -> ANN-assisted search.
- [x] Assert reused point payload refreshes to the latest `build_id` without vector rewrite.
- [x] Assert changed/new point upsert and stale point delete behavior.
- [x] Assert ANN-assisted search after rebuild uses current graph ids and local WAVE-RAG final ranking.
- [x] Make minimal production or test-support fixes only if the new regression exposes a defect.
- [x] Update README/spec only if behavior or operator expectations change.

## Validation

Focused tests:

```bash
uv run pytest tests/unit/test_storage_state.py tests/unit/test_manual_library.py tests/unit/test_api.py -q
```

Likely new/updated test target:

```bash
uv run pytest tests/unit/test_manual_library.py -q
```

Final check:

```bash
uv run pytest tests/ -q
```

## Review Gates

- Confirm no live Qdrant dependency was introduced into the default test suite.
- Confirm reused payload-only refreshes still count as `points_reused`.
- Confirm Qdrant scores are never used as final `/search` ranking scores.
- Confirm stale Qdrant node ids cannot leak into final search results.
- Confirm no raw query text, chunk text, vectors, secrets, or unsafe payload fields are logged or stored.

## Rollback Points

- If integration setup becomes too broad, keep M17 as a focused unit/integration hybrid using `FakeQdrantClient`.
- If a production defect is discovered but the fix is larger than expected, capture it as a follow-up and keep M17 limited to a failing regression if the team wants a red test first.
