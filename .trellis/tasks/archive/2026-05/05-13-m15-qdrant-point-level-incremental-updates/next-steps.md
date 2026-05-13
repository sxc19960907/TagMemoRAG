# next-steps.md - M15 Follow-up Plan

## Review Summary

Reviewed M15 Qdrant point-level incremental sync against the archived PRD/design and the current backend storage spec.

The main rebuild ordering is sound:

- Managed-library Qdrant rebuilds build the new `GraphState` in memory first.
- Qdrant sync runs before graph/meta/identity/report artifacts are saved.
- Stale deletes run after required current point upserts.
- Qdrant sync failures keep the old served graph active and leave dirty library state pending.
- `load_kb()` continues to retrieve by graph node ids and fail clearly when Qdrant vectors are missing.

## Fix Applied

Found one M15 contract drift:

- Point-incremental sync skipped reused vectors entirely, including payload refresh.
- That preserved vector-write savings, but reused Qdrant points kept the old `build_id` payload even after a successful new build.
- This made Qdrant payload inspection inconsistent with the current built KB state.

Fix:

- Added `QdrantVectorStore.update_payloads(ids, payloads)`.
- During `point_incremental` sync, reused node ids now refresh safe payload fields only.
- Reused vectors are still not rewritten.
- Existing sync counts remain unchanged: refreshed payload-only reused points still count as `points_reused`, not `points_upserted`.

## Validation

Focused validation passed:

```bash
uv run pytest tests/unit/test_storage_state.py tests/unit/test_manual_library.py -q
```

Result: `25 passed`.

## Next Plan

1. Finish M16 review after M15 payload refresh lands.
   - Confirm ANN preselection uses only current graph node ids.
   - Confirm ANN fallback remains exact local WAVE-RAG when Qdrant query fails or returns unusable candidates.
   - Confirm M16 does not depend on stale `build_id` payload semantics.

2. Add an integration-style fake-client regression for M15 plus M16 together.
   - Build Qdrant-backed library baseline.
   - Run incremental rebuild with one changed chunk and one reused chunk.
   - Verify reused point payload has the latest `build_id`.
   - Run ANN-assisted search and verify final ranking still comes from local WAVE-RAG.

3. Consider a Qdrant payload maintenance follow-up.
   - Batch payload refresh for reused points if large rebuilds make per-point `set_payload` calls too chatty.
   - Keep the current implementation until profiling shows this is a real operational issue.
   - Preserve the current safety rule: payload refresh must complete before stale deletes and before graph/meta save.

4. Document operational inspection expectations if Qdrant becomes an operator-facing dependency.
   - `build_id` identifies the build that last confirmed a point.
   - `points_reused` may still have refreshed payloads without vector rewrites.
   - Payloads remain non-textual and must not contain raw chunk text, vectors outside Qdrant's vector field, or secrets.
