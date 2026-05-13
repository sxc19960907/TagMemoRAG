# design.md - M17 Qdrant Incremental + ANN Integration Regression

## Scope

M17 is primarily a regression and integration-hardening task. It should validate the combined behavior of Qdrant point-level incremental rebuilds and Qdrant ANN preselection without changing the product surface unless the regression reveals a real defect.

## Target Flow

```text
managed library baseline
  -> Qdrant-backed build/rebuild
  -> Qdrant points include safe payloads for build A
  -> mutate one manual while leaving one chunk reusable
  -> incremental managed-library rebuild
  -> point_incremental Qdrant sync
       - upsert changed/new points
       - refresh payloads for reused points
       - delete stale points after safe upserts
  -> graph/meta/chunk_identity saved for build B
  -> ANN-assisted search
       - Qdrant returns candidate node ids
       - candidates are checked against current graph ids
       - local WAVE-RAG ranks final results
```

## Existing Contracts To Preserve

- Qdrant payloads are safe only: `kb_name`, `node_id`, `build_id`, `chunk_identity_key`, `manual_id`, `source_file`, and `text_hash`.
- Reused points are not vector-rewritten during point-incremental sync.
- Reused points still refresh safe payload fields.
- Reused payload-only refreshes count as `points_reused`, not `points_upserted`.
- Qdrant sync completes before graph/meta artifacts are saved and before the serving state swaps.
- ANN candidate ids are advisory; Qdrant scores must not become final search scores.
- ANN fallback stays exact local WAVE-RAG when Qdrant search fails or candidates are invalid.

## Test Design

Use the existing `FakeQdrantClient` pattern from `tests/unit/test_storage_state.py`.

Recommended test shape:

1. Create a temporary managed-library root with two manuals or one manual with multiple stable chunks.
2. Configure:
   - `vector_store.provider=qdrant`
   - fake Qdrant client
   - hashing embedder
   - `search.ann_preselect_enabled=true`
   - small `ann_candidate_k` to make stale/candidate behavior observable
3. Run an initial managed-library rebuild or equivalent build+save path that writes:
   - graph
   - vectors
   - chunk identity
   - Qdrant points
4. Capture:
   - initial `build_id`
   - a reusable node id and its vector/payload
   - point upsert/delete/set-payload calls
5. Mutate one manual chunk and mark the library dirty through existing library helpers or API/CLI path.
6. Run incremental rebuild.
7. Assert:
   - `effective_mode=incremental`
   - `qdrant_sync.strategy=point_incremental`
   - reused point vector is unchanged
   - reused point payload `build_id` equals new `GraphState.build_id`
   - changed/new point was upserted
   - stale node ids were deleted
8. Run ANN-assisted search against the new state.
9. Assert:
   - returned node ids are current graph ids
   - a result that should win by local WAVE-RAG ranking wins even if fake Qdrant candidate score ordering is not itself the final ranking

## Data Setup Notes

Prefer deterministic manual content that produces predictable chunk identity:

- Keep one chunk text and metadata unchanged so it is reusable.
- Change one chunk text enough to force a new text hash.
- Avoid relying on real embedding model downloads; use existing hashing/fake embedder fixtures.

If exact node-id reuse is hard to guarantee through high-level helpers, the test may inspect `chunk_identity.json` to select the reused node id after rebuild. The assertion should be about the persisted contract, not assumptions about a specific hard-coded node id.

## Production Change Policy

M17 should not proactively refactor production code. Acceptable production changes are limited to:

- fixes required for the new regression to pass when it exposes contract drift
- small testability hooks that follow existing patterns
- documentation/spec updates if observed behavior differs from documented behavior

## Rollout / Rollback

No runtime rollout is expected because this is a regression-hardening milestone. If a production fix is needed, keep existing config defaults and fallback behavior unchanged so operators can still disable ANN or use NPZ.
