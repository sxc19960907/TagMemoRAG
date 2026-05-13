# design.md - M18 Qdrant Payload Maintenance / Batch Refresh

## Scope

M18 improves the efficiency and observability of reused-point payload refreshes in Qdrant-backed managed-library incremental rebuilds. It should preserve all M15/M17 correctness guarantees while reducing remote call count when many points are reused.

## Current Flow

```text
incremental managed-library rebuild
  -> build new GraphState in memory
  -> compute reusable node ids from chunk_identity
  -> upsert changed/new vectors with current payloads
  -> for each reused node id:
       client.set_payload(collection, points=[id], payload=safe_payload)
  -> delete stale ids
  -> save graph/meta/identity/report
  -> swap served GraphState
  -> clear dirty state
```

The flow is safe, but the reused payload refresh is O(reused points) remote calls.

## Existing Contracts To Preserve

- Qdrant payload fields remain safe only: `kb_name`, `node_id`, `build_id`, `chunk_identity_key`, `manual_id`, `source_file`, and `text_hash`.
- Reused vectors are not rewritten.
- Reused payload-only refreshes count as `points_reused`, not `points_upserted`.
- Changed/new points are still upserted before stale deletes.
- Reused payload refreshes must complete before stale deletes and before graph/meta artifacts are saved.
- Qdrant sync failure keeps the old served graph active and dirty library state pending.
- NPZ storage behavior stays unchanged.

## Proposed Storage Contract

Keep the public storage call shape:

```python
QdrantVectorStore.update_payloads(ids, payloads)
```

Inside the Qdrant implementation, choose the best available client strategy:

1. **Batch strategy** for clients that can update multiple points with distinct payloads safely.
2. **Per-point strategy** for clients that only expose shared-payload `set_payload` or where capability detection is uncertain.

The method should be atomic from the caller's perspective: any raised exception means the rebuild must fail before stale deletion or graph swap. It does not need to roll back payloads already applied by Qdrant because the old graph remains loadable and payloads are inspection metadata, not vector data.

## Candidate Batch Strategy

Implementation should research the installed qdrant-client model support before coding. A likely approach is to use an operation-oriented endpoint when available, such as a batch update/update-points API that accepts multiple `SetPayloadOperation` items, each with:

- a single point id selector
- that point's safe payload

This preserves distinct payloads while reducing HTTP round trips. The implementation must not use a shared-payload multi-point `set_payload` call unless all payload dictionaries are identical, which is not expected for reused points because `node_id` and identity fields differ.

Suggested helper shape:

```python
def _update_payloads_batch(self, ids: np.ndarray, payloads: list[dict[str, Any]]) -> int:
    ...
```

Return value can represent remote-style call count or operation count if needed for reporting. If the client lacks required attributes/imports, raise `NotImplementedError` internally and fall back to per-point.

## Capability Detection

Use duck typing and import guards rather than hard version checks where practical:

- Check whether the client exposes the batch update method.
- Check whether required qdrant-client model classes can be imported.
- Keep fake-client support explicit and small so tests can simulate both paths.

Avoid network probing. Capability detection must not create or mutate collections.

## Reporting Design

The existing Qdrant sync summary may remain unchanged if tests can observe call reduction through the fake client. If reporting is extended, use additive fields only:

```json
{
  "provider": "qdrant",
  "strategy": "point_incremental",
  "points_upserted": 1,
  "points_deleted": 0,
  "points_reused": 120,
  "fallback_reason": "",
  "payload_refresh_strategy": "batch",
  "payload_refresh_calls": 1,
  "payloads_refreshed": 120
}
```

Recommended values:

- `payload_refresh_strategy`: `batch`, `per_point`, `none`, or `skipped`
- `payload_refresh_calls`: low-cardinality integer count of remote-style calls attempted
- `payloads_refreshed`: count of reused payloads refreshed

If these fields add too much churn to API/CLI expectations, keep them internal to tests and defer response/report expansion.

## Failure Ordering

The safe sequence should remain:

```text
upsert changed/new vectors
  -> refresh reused payloads
  -> delete stale ids
  -> save graph/meta/identity/report
  -> swap graph
  -> clear dirty state
```

Failure matrix:

- Upsert failure: no payload refresh or stale delete required; old graph remains active.
- Payload batch/per-point failure: no stale delete; old graph remains active; dirty state remains pending.
- Stale delete failure: graph must not swap; dirty state remains pending.
- Save failure after Qdrant sync: old graph remains active; collection may already contain new payloads/upserts, which is acceptable under existing M15 partial-sync tolerance as long as old graph node ids remain loadable.

## Test Design

Use the existing `FakeQdrantClient` pattern.

Recommended additions:

1. Add fake-client batch payload operation support and call tracking.
2. Unit test `QdrantVectorStore.update_payloads()`:
   - batch-capable fake client receives one batch-style call for multiple ids
   - per-point fallback still calls `set_payload` per id when batch support is disabled
   - safe payload allowlist still strips unsafe fields
3. Managed-library regression:
   - build Qdrant baseline with multiple reusable chunks
   - run point-incremental rebuild with many reused ids
   - assert vectors for reused points are unchanged
   - assert payload `build_id` refreshes for reused points
   - assert `points_reused` count remains correct and `points_upserted` excludes reused ids
4. Failure regression:
   - make fake batch payload refresh fail
   - assert stale deletes are not called
   - assert task fails, old `GraphState` remains active, and manifest pending state remains true

## Rollout / Rollback

- No config flag is required for MVP; the client should automatically use batch when safe and fallback when unavailable.
- Rollback is straightforward: force the implementation to the current per-point strategy.
- Operators can continue using full rebuild or NPZ if Qdrant-specific behavior is problematic.
- Existing collections need no migration.

## Open Implementation Questions

- Which qdrant-client batch update API is available in the pinned/installed dependency set?
- Should additive payload refresh reporting be exposed in task/meta/report now, or kept as test-observable internal behavior?
- Should batch size be bounded for very large reused sets, or is one operation list acceptable for the expected local deployment size?
