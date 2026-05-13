# M17 Qdrant Incremental + ANN Integration Regression

## Goal

Add integration-style regression coverage for the combined M15 and M16 Qdrant path: managed-library incremental rebuilds must keep Qdrant point payloads current, and ANN-assisted search after that rebuild must still use Qdrant only as a candidate generator while local WAVE-RAG remains the final ranking engine.

## Background / Known Context

- M15 added Qdrant point-level incremental sync for managed-library rebuilds.
- M15 follow-up review found and fixed a payload drift risk: reused points must refresh safe payload fields, including `build_id`, even when vectors are not rewritten.
- M16 added optional Qdrant ANN preselection for search.
- M16 explicitly preserves local WAVE-RAG as the final ranker and uses Qdrant ANN only to narrow eligible candidates.
- Existing tests cover M15 and M16 separately, but the combined rebuild-then-search path is the most important remaining Qdrant boundary.
- The default test suite must not require a live Qdrant service; use the existing fake Qdrant client pattern.

## Requirements

### 1. Combined Incremental Rebuild + ANN Scenario

- Add a regression that starts from a Qdrant-backed managed-library KB.
- Perform an initial successful library rebuild or build that writes Qdrant points.
- Change one manual chunk while leaving at least one chunk reusable under the chunk identity rules.
- Run an incremental managed-library rebuild with Qdrant enabled.
- Confirm the rebuild uses the point-incremental sync path when identity data is compatible.

### 2. Reused Point Payload Freshness

- Verify a reused Qdrant point keeps its vector unchanged.
- Verify the same reused point receives updated safe payload fields for the new build.
- At minimum, assert the reused point payload `build_id` matches the current served `GraphState.build_id`.
- Preserve the M15 counting contract: payload-only reused points count as `points_reused`, not `points_upserted`.

### 3. Changed and Stale Point Safety

- Verify changed or new node ids are upserted.
- Verify stale node ids are deleted only after required current upserts succeed.
- Preserve the existing failure behavior: Qdrant sync failures must keep the old served graph active and leave dirty state pending.
- Do not introduce raw chunk text, vectors outside the Qdrant vector field, secrets, or high-cardinality source paths into payload assertions beyond already-safe payload fields.

### 4. ANN-Assisted Search After Incremental Rebuild

- Enable `search.ann_preselect_enabled=true` with `vector_store.provider=qdrant`.
- Run search after the incremental rebuild.
- Verify Qdrant ANN candidate retrieval uses only current graph node ids.
- Verify final result ordering is still produced by local WAVE-RAG over the loaded graph and vectors.
- Verify the test would fail if stale Qdrant candidates or approximate Qdrant scores became final results.

### 5. Regression Scope and Compatibility

- Keep NPZ behavior unchanged.
- Do not add a live Qdrant dependency to the default test suite.
- Prefer focused test-support improvements over production changes unless the new regression reveals a real defect.
- Keep API and CLI response schemas unchanged in this milestone.

## Acceptance Criteria

- [ ] A fake-client integration regression covers Qdrant-backed baseline build, incremental rebuild, and ANN-assisted search in one flow.
- [ ] The regression proves reused Qdrant points refresh `build_id` payload without rewriting vectors.
- [ ] The regression proves changed/new points are upserted and stale points are cleaned up safely.
- [ ] The regression proves ANN-assisted search after incremental rebuild does not return stale node ids.
- [ ] The regression proves final ranking remains local WAVE-RAG based rather than remote Qdrant score based.
- [ ] Existing M15 and M16 focused tests still pass.
- [ ] `uv run pytest tests/ -q` passes.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- Test coverage captures the M15/M16 combined contract.
- Any production change discovered by the regression is small, documented, and covered by focused tests.
- README/spec updates are added only if behavior or operator expectations change.

## Out of Scope

- Implementing batch Qdrant payload refresh.
- Adding Qdrant payload-filtered ANN.
- Changing search response schemas.
- Replacing WAVE-RAG final ranking with Qdrant ranking.
- Requiring live Qdrant in CI or the default local test suite.
- Adding new production dependencies.

## Research References

- `.trellis/tasks/archive/2026-05/05-13-m15-qdrant-point-level-incremental-updates/next-steps.md`
- `.trellis/tasks/archive/2026-05/05-13-m15-qdrant-point-level-incremental-updates/prd.md`
- `.trellis/tasks/archive/2026-05/05-13-m16-qdrant-ann-preselection/prd.md`
- `.trellis/spec/backend/database-guidelines.md`
