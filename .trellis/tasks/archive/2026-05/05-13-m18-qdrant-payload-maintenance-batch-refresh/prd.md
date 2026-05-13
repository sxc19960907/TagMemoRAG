# M18 Qdrant Payload Maintenance / Batch Refresh

## Goal

Optimize Qdrant payload maintenance for reused points during managed-library point-incremental rebuilds. Reused points must still refresh safe payload fields such as `build_id`, but large rebuilds should avoid issuing one remote `set_payload` call per reused point when a supported Qdrant client can update payloads in batches.

## Background / Known Context

- M15 added Qdrant point-level incremental sync for managed-library rebuilds.
- The M15 follow-up fixed payload drift by adding payload-only refreshes for reused points.
- M17 added a combined regression proving reused vectors are not rewritten, reused payloads refresh to the current `build_id`, stale points are deleted safely, and ANN-assisted search still treats Qdrant as a candidate generator.
- Current `QdrantVectorStore.update_payloads()` refreshes reused points by looping over ids and calling `client.set_payload(...)` once per point.
- Per-point refresh is correct but can become chatty for large mostly-reused rebuilds.
- Payload fields must stay limited to the safe allowlist: `kb_name`, `node_id`, `build_id`, `chunk_identity_key`, `manual_id`, `source_file`, and `text_hash`.

## Requirements

### 1. Batch Payload Refresh Capability

- Add a Qdrant payload refresh path that can group reused-point payload updates when the installed client and fake client support the needed operation.
- Keep `QdrantVectorStore.update_payloads(ids, payloads)` as the storage-layer boundary unless implementation research proves a narrow new method is cleaner.
- Preserve per-point fallback for fake clients, older qdrant-client versions, and any client shape that cannot safely apply per-point distinct payloads in one batch.
- Do not introduce a live Qdrant service dependency into the default test suite.

### 2. Per-Point Payload Semantics

- Each reused point must receive its own safe payload, including its own `node_id`, `chunk_identity_key`, `manual_id`, `source_file`, and `text_hash`.
- A batch implementation must not accidentally apply one shared payload to multiple points when their payloads differ.
- Reused points must not rewrite vectors.
- Payload-only refreshes must continue to count as `points_reused`, not `points_upserted`.

### 3. Safety Ordering and Failure Behavior

- Managed-library Qdrant sync must still complete before graph/meta/identity/report artifacts are saved and before the serving state swaps.
- Reused payload refresh must complete before stale point deletes.
- Stale deletes must still run only after required current upserts and reused payload refreshes succeed.
- If payload refresh fails, the old served `GraphState` must remain active and dirty library state must remain pending.
- Partial payload refresh failure may leave some reused points with newer payloads, but it must not delete stale points or swap to a new graph.

### 4. Observability and Reporting

- Extend Qdrant sync reporting only if useful and additive.
- Existing fields must remain compatible: `provider`, `strategy`, `points_upserted`, `points_deleted`, `points_reused`, and `fallback_reason`.
- If new fields are added, prefer low-cardinality operational fields such as `payload_refresh_strategy`, `payload_refresh_calls`, or `payloads_refreshed`.
- Do not log or report raw chunk text, vectors, secrets, raw query text, or high-cardinality absolute source paths.

### 5. Compatibility

- NPZ behavior must remain unchanged.
- Existing API and CLI response schemas may receive additive metadata only if it materially improves operator visibility.
- Existing Qdrant collections must remain load-compatible.
- Default local and CI tests must continue using fake clients and must not require network access.
- Do not add new production dependencies.

## Acceptance Criteria

- [ ] Reused Qdrant points can refresh safe payloads through a batch-capable path when available.
- [ ] Fake-client coverage proves batch refresh reduces remote-style payload calls for multiple reused points.
- [ ] Fallback coverage proves per-point refresh still works when batch support is unavailable.
- [ ] Regression coverage proves reused vectors are not rewritten and payload `build_id` updates to the current build.
- [ ] Failure coverage proves payload refresh failure prevents stale deletes, preserves the old served graph, and leaves dirty state pending.
- [ ] Qdrant sync counts preserve the M15 contract: payload-only reused points count as `points_reused`, not `points_upserted`.
- [ ] Existing M15/M17 Qdrant incremental tests still pass.
- [ ] `uv run pytest tests/ -q` passes.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- Batch and fallback behavior are covered by fake-client tests.
- Production changes are limited to Qdrant storage/sync support needed for payload refresh efficiency.
- README/spec updates are added only if behavior or operator expectations change.

## Out of Scope

- Adding Qdrant payload-filtered ANN search.
- Changing WAVE-RAG search ranking semantics.
- Changing graph, vector, or API response schemas beyond optional additive rebuild metadata.
- Requiring a live Qdrant service in default tests.
- Cleaning orphaned Qdrant points when old graph state is unavailable.
- Replacing point ids or changing node-id-to-Qdrant-id mapping.

## Research References

- `.trellis/workspace/suixingchen/roadmap.md`
- `.trellis/tasks/archive/2026-05/05-13-m15-qdrant-point-level-incremental-updates/design.md`
- `.trellis/tasks/archive/2026-05/05-13-m15-qdrant-point-level-incremental-updates/next-steps.md`
- `.trellis/tasks/archive/2026-05/05-13-m17-qdrant-incremental-ann-integration-regression/prd.md`
- `.trellis/tasks/archive/2026-05/05-13-m17-qdrant-incremental-ann-integration-regression/design.md`
- `.trellis/spec/backend/database-guidelines.md`
