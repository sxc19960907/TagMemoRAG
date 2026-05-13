# implement.md - M15 Qdrant Point-Level Incremental Updates

## Implementation Checklist

- [x] Read backend specs with `trellis-before-dev` before coding.
- [x] Review M9 Qdrant backend and M14 identity/impact code paths.
- [x] Add or extend Qdrant vector store methods for explicit point `delete()` and selective `update()`/upsert.
- [x] Add Qdrant payload construction that includes safe build/chunk identity fields.
- [x] Keep old Qdrant collections load-compatible when payload fields are missing.
- [x] Add a Qdrant sync summary dataclass or compact dict contract.
- [x] Wire Qdrant sync summary into `RebuildTask.to_dict()`.
- [x] Add sync summary to `meta.json` or `rebuild_impact.json` after successful managed-library rebuilds.
- [x] Compute stale node ids from `old_state` and `new_state`.
- [x] Compute new/changed node ids from M14 identity/impact data when available.
- [x] Implement `point_incremental` sync for safe Qdrant-backed managed-library rebuilds.
- [x] Implement `full_sync` fallback for missing/unsafe identity or impact data.
- [x] Ensure stale deletes happen only after required upserts succeed.
- [x] Preserve NPZ behavior and existing `save_kb()` / `load_kb()` contracts.
- [x] Make Qdrant operation failures produce structured project errors.
- [x] Update README with Qdrant point-level sync semantics and rollback note.
- [x] Update backend spec for Qdrant payload/sync contract.

## Validation

Focused tests:

- `uv run pytest tests/unit/test_storage_state.py -q`
- `uv run pytest tests/unit/test_manual_library.py -q`
- `uv run pytest tests/unit/test_manual_library_api.py -q`
- `uv run pytest tests/unit/test_cli.py -q`

Add tests for:

- fake Qdrant client records enriched payloads on upsert
- explicit stale point deletion after a successful managed-library rebuild
- incremental sync skips reused points and upserts changed/new points
- missing identity/impact falls back to full sync with reason metadata
- failed Qdrant sync leaves rebuild failed and dirty state pending
- NPZ provider regression

Final check:

- `uv run pytest tests/ -q`

## Review Gates

- Confirm no raw chunk text is stored in Qdrant payload or rebuild metadata.
- Confirm WAVE-RAG result ranking logic is unchanged.
- Confirm stale deletion cannot run before all required current points are upserted.
- Confirm old Qdrant collections without enriched payloads remain loadable.
- Confirm metrics labels remain low-cardinality.

## Rollback Points

- If selective point sync is too risky, keep full-sync cleanup only for Qdrant and report `strategy=full_sync`.
- If Qdrant delete support is unreliable in fake/client versions, ship enriched payloads and full upsert first, leaving stale cleanup behind a follow-up.
- Operators can switch `vector_store.provider=npz` or run `mode=full` while point-level optimization is debugged.
