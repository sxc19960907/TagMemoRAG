# implement.md - M13 Incremental Manual Rebuild/Update Path

## Implementation Checklist

- [x] Read current backend specs with `trellis-before-dev` before coding.
- [x] Add/extend manifest dirty-state dataclasses and serialization in `manual_library.py` or a new `incremental_rebuild.py`.
- [x] Update `ManualLibraryManifest.from_dict()` / `to_dict()` to preserve backward compatibility with old manifests.
- [x] Extend `mark_pending()` or add `mark_dirty()` to record dirty manual IDs/source files/operation/checksum.
- [x] Wire dirty tracking into:
  - [x] `upsert_manual`
  - [x] `update_manual_metadata`
  - [x] `replace_manual_file`
  - [x] `disable_manual`
  - [x] `delete_manual`
  - [x] bulk import commit paths
  - [x] tag rewrite paths if sidecar metadata changes should rebuild only affected manuals
- [x] Add `src/tagmemorag/incremental_rebuild.py` with:
  - [x] dirty state loading/planning
  - [x] reusable old chunk/vector extraction
  - [x] dirty active manual parse/embed
  - [x] inactive/deleted manual removal
  - [x] deterministic final chunk/vector ordering
  - [x] global `build_graph()` call
  - [x] anchor reconcile
  - [x] fallback metadata
- [x] Extend `RebuildTask` with mode/detail metadata.
- [x] Add `build_kb_incremental()` or a shared build service invoked by `start_library_rebuild()`.
- [x] Extend `start_library_rebuild()` with `mode` and `allow_fallback`.
- [x] Ensure successful incremental rebuild calls `save_kb()`, swaps graph, clears pending and dirty state only after success.
- [x] Ensure failed incremental rebuild preserves old graph and dirty state.
- [x] Ensure NPZ persistence writes the final full vector matrix correctly.
- [x] Decide and test Qdrant behavior for stale point IDs:
  - [x] load by graph node IDs must ignore stale old points
  - [ ] optional collection recreate/delete is safe and documented (deferred to M14/Qdrant optimization follow-up)
- [x] Extend API request/response models for rebuild mode and fallback.
- [x] Add API tests for full/incremental/auto modes, auth, fallback, and task metadata.
- [x] Add CLI managed-library rebuild helper returning JSON.
- [x] Extend manual library admin UI controls for rebuild mode and dirty count/status.
- [x] Update README with API/CLI/UI examples and fallback semantics.
- [x] Update backend specs if dirty manifest or incremental rebuild conventions should persist.

## Suggested Implementation Order

1. **Dirty Tracking**
   - Extend manifest schema in a backward-compatible way.
   - Add unit tests that each manual mutation records dirty state.
   - Include bulk import and tag rewrite if they mutate sidecars.

2. **Incremental Core**
   - Create a pure service that takes `kb_name`, `cfg`, `embedder`, `old_state`, and dirty state.
   - Make it return `(GraphState, detail)`.
   - Test it without API first using small fixture manuals.

3. **Equivalence Tests**
   - Build a KB full.
   - Mutate one manual.
   - Run incremental.
   - Run full rebuild into an isolated temp dir.
   - Compare searchable results/eval metrics and key graph invariants rather than fragile raw node IDs.

4. **State/API/CLI Wiring**
   - Extend rebuild task metadata.
   - Wire mode and fallback into `start_library_rebuild`.
   - Add FastAPI and CLI tests.

5. **Admin UI and Docs**
   - Add rebuild mode selector and dirty count display.
   - Keep existing manual library flows intact.
   - Document operational guidance.

## Validation

Focused tests to add/run:

- `uv run pytest tests/unit/test_manual_library.py -q`
- `uv run pytest tests/unit/test_incremental_rebuild.py -q`
- `uv run pytest tests/unit/test_manual_library_api.py -q`
- `uv run pytest tests/unit/test_manual_bulk_import.py tests/unit/test_tag_governance.py -q`
- `uv run pytest tests/unit/test_cli.py tests/unit/test_manual_library_ui.py -q`
- `uv run pytest tests/e2e/test_eval_cli.py -q`

Final check:

- `uv run pytest tests/ -q`

Manual smoke:

1. Start FastAPI with hashing embedder.
2. Upload a new manual.
3. Trigger `POST /manual-library/rebuild {"mode":"incremental"}`.
4. Confirm `/manual-library` pending clears and `/search` finds new content.
5. Replace one manual file and rebuild incremental again.
6. Compare search/eval behavior with a full rebuild.

## Review Gates

- Before coding: confirm default API mode remains `full` for compatibility, with explicit `incremental` opt-in.
- Before finalizing core: verify incremental graph construction recomputes global edges rather than patching local edges only.
- Before exposing UI controls: verify dirty count cannot mislead operators when dirty state is missing and fallback full rebuild will happen.
- Before finish: inspect saved `meta.json` and manifest after full, incremental, fallback, and failed rebuilds.

## Rollback Points

- Dirty tracking can ship before incremental rebuild if it is backward-compatible and full rebuild ignores dirty details.
- Incremental service can stay API-hidden until equivalence tests are strong.
- API can expose `mode=incremental` before changing any UI default.
- If Qdrant point-level cleanup is risky, defer cleanup and rely on graph-node-id loading for correctness.

## Known Edge Cases To Test

- Metadata-only change that affects filters/tags but not source content.
- Source file rename in metadata update.
- Manual disabled then re-enabled before rebuild.
- Manual hard-deleted after dirty state was recorded.
- Dirty state references a manual ID no longer present.
- Bulk import updates multiple manuals and creates one new manual.
- Tag rewrite changes tags across many sidecars.
- Existing manifest has `pending_changes=true` but no dirty map.
- Old `GraphState` missing a vector for one node.
- Empty KB after all manuals are disabled.

## Completion Notes

- Implemented M13 MVP in code, API, CLI, admin UI, tests, README, and backend spec.
- Query cache is cleared for the rebuilt KB after successful graph swap.
- Incremental mode reuses unchanged manual chunks/vectors and rebuilds final graph topology globally.
- Fallback metadata is surfaced in rebuild tasks and persisted in `meta.json`.
- Validation: `uv run pytest tests/ -q` -> 159 passed.
- Follow-up enhancements moved to M14: chunk identity map, threshold-based auto mode, rebuild impact report, dirty-state export, and Qdrant point-level cleanup.
