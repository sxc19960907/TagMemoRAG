# T1 — IndexGeneration mechanism + ID system split — Design

This document is the technical design for the task. It implements the contracts defined in `.trellis/spec/backend/architecture.md` § A1 and § A4, parameterized by the eight brainstorm decisions D1–D8 captured in `prd.md`.

## 1. Goal & Boundaries

**In scope:** chunk_id audit; vector_point_id introduction (Qdrant point id replacement); generation-aware Qdrant collection naming; per-KB `index.json` index; `{kb_root}/g{N}/...` directory layout; AppState dual-generation slot; shadow build path reusing existing rebuild flow; 5 admin endpoints (build-shadow / cancel-shadow / swap / retire / status); Settings sync on swap; lazy idempotent migration to g1.

**Out of scope:** real-flow traffic split (deferred indefinitely per architecture-v2 D5); T5 replay tool; T2 QueryPlan / Reranker / `/answer`; any change to architecture.md itself.

**Compatibility:** existing single-collection KBs migrate via D1 (rename + alias) without rebuild; existing `/search` and `/retrieve` behavior preserved.

## 2. Data Layout

### 2.1 File system

```
{settings.storage.data_dir}/
  index.json                                # NEW: KB-level index (D2)
  g{N}/                                    # NEW: per-generation subdir
    graph.json
    vectors.npz                            # if NPZ backend
    chunk_identity.json
    epa_basis.npz
    tag_embeddings.npz
    tag_cooccurrence.json
    tag_intrinsic_residuals.npz
    anchors/                               # existing anchor files
    rebuild_impact.json
  qdrant_pointer.json                      # NEW: if Qdrant backend, records collection name `{prefix}_{kb}_g{N}`
```

`{kb_root}` is per-KB; multi-KB deployments have one `{kb_root}` per KB. Existing per-KB convention preserved.

### 2.2 Qdrant collections

- New naming: `{prefix}_{kb}_g{N}` produced by `collection_name(prefix, kb, generation)`.
- Migration (D1): on first startup after this change, for each existing KB:
  1. Detect legacy collection `{prefix}_{kb}` (no `_g` suffix) and absence of `index.json`.
  2. Create Qdrant **alias** `{prefix}_{kb}_g1 → {prefix}_{kb}` via `qdrant_client.create_alias`.
  3. Move legacy file artifacts into `{kb_root}/g1/`.
  4. Write `index.json` with `active_generation=1`.
  5. All subsequent reads/writes go through `{prefix}_{kb}_g1` (resolved via alias to the legacy underlying collection).
- Migration is idempotent: if `index.json` already exists, skip.
- Future swaps create real new collections; the legacy underlying collection name remains hidden behind the g1 alias until the day g1 is retired (then the alias and the underlying collection are both deleted).

### 2.3 `index.json` schema

```jsonc
{
  "schema_version": 1,
  "kb_name": "default",
  "active_generation": 2,
  "shadow_generation": 3,         // null when no shadow exists
  "generations": {
    "1": {
      "created_at": "2026-05-17T10:00:00Z",
      "swap_at": "2026-05-17T10:00:00Z",       // initial generation: created_at == swap_at
      "retired_at": "2026-05-18T10:30:00Z",
      "parser_version": "v3",
      "chunker_version": "v2",
      "embedding_model_id": "bge-m3",
      "embedding_model_version": "v1.0",
      "index_schema_version": 4,
      "chunk_count": 1234,
      "build_id": "20260517100000123456"
    },
    "2": {
      "created_at": "2026-05-18T10:00:00Z",
      "swap_at": "2026-05-18T10:30:00Z",
      "retired_at": null,
      "parser_version": "v3",
      "chunker_version": "v2",
      "embedding_model_id": "bge-m3",
      "embedding_model_version": "v1.1",
      "index_schema_version": 4,
      "chunk_count": 1240,
      "build_id": "20260518100000789012"
    },
    "3": {
      "status": "building",                    // "building" | "ready" | "failed"
      "progress": 0.45,                        // 0..1, monotonic
      "build_started_at": "2026-05-18T11:00:00Z",
      "trigger_diff": ["embedding_model_version"],
      "requested_by": "admin",                 // optional, audit field
      "task_id": "uuid-of-rebuild-task",
      "error": null                            // structured ServiceError dict when status=failed
    }
  }
}
```

Invariants:

- `active_generation` is always a key in `generations` whose entry is "ready" (has `swap_at`, no `status` field).
- `shadow_generation` is null OR a key whose entry has `status` field.
- A generation key is either "ready-shape" (with version snapshot) or "shadow-shape" (with status); never both shapes at once.
- A "ready-shape" entry MUST contain a non-null `swap_at` (used by D4 retire window check).
- `retired_at` is set only on retire; once set the generation is no longer addressable.
- All writes go through `storage/atomic.atomic_write` to prevent partial files.
- `index.json` size is bounded: history entries with `retired_at` set may be trimmed if `len(generations) > settings.indexgen.history_max` (default 20). Trimming removes oldest retired entries.

## 3. ID Derivation

### 3.1 chunk_id (audit)

Current implementation (`src/tagmemorag/chunk_identity.py:parser_signature`) already excludes embedder fields. This task only **locks** that contract:

- Add a regression test (`tests/unit/test_chunk_identity.py::test_chunk_id_does_not_change_when_embedder_changes`): build chunk identity twice with different `embedder` settings but identical parser/chunker/source; assert chunk_id equal.
- Add a doc comment in `chunk_identity.py` referencing architecture A1.

No code change to derivation function.

### 3.2 vector_point_id (new, payload-only)

```python
# src/tagmemorag/vector_id.py
def vector_point_id(chunk_id: str, embedding_model_id: str, embedding_model_version: str) -> str:
    h = hashlib.sha256()
    h.update(chunk_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(embedding_model_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(embedding_model_version.encode("utf-8"))
    return str(uuid.UUID(bytes=h.digest()[:16]))
```

**Storage role (decided in Slice 1.5 review):** `vector_point_id` is a **payload field**, not the Qdrant point id. Per architecture.md § A1 "Storage role of vector_point_id":

- A4 collection-per-generation already isolates embedder versions; `node_id` within one collection is unambiguous.
- Promoting `vector_point_id` to Qdrant point id would force a UUID-vs-int type change across every call site (`delete`, `update_payloads`, `load`, `_scroll_ids`, `get`, `FakeQdrantClient`) for no additional isolation guarantee.
- Therefore the Qdrant point id remains `int(node_id)` (unchanged). `vector_point_id` lives in the payload (added to `SAFE_QDRANT_PAYLOAD_KEYS` in Slice 1).
- Cross-generation tools (eval replay, debug joins) read the payload field to match rows across `g{N}` collections.

NPZ backend: same principle. Vector ordering keyed by `node_id`; a parallel `vector_point_ids` array is added next to `vectors.npz` only when a tool actually needs it (deferred).

**Slice 1.5 (point id type migration) is removed from this task.** The contract is delivered by Slice 1 alone (payload field) plus this design note.

## 4. AppState Dual-Generation Model

`AppState` (current `src/tagmemorag/state.py:124`) gains:

```python
@dataclass
class AppState:
    # existing fields preserved
    current: GraphState | None = None
    kbs: dict[str, GraphState] = field(default_factory=dict)
    # new fields:
    shadow_kbs: dict[str, GraphState] = field(default_factory=dict)
    generation_meta: dict[str, GenerationMeta] = field(default_factory=dict)  # in-memory cache of index.json per kb

    def get_kb(self, kb_name: str) -> GraphState:
        # unchanged: returns active GraphState
        ...

    def get_shadow_kb(self, kb_name: str) -> GraphState | None:
        with self._lock:
            return self.shadow_kbs.get(kb_name)

    def install_shadow(self, kb_name: str, shadow_state: GraphState) -> None:
        # called when shadow build completes successfully
        with self._lock:
            self.shadow_kbs[kb_name] = shadow_state

    def swap_generation(self, kb_name: str) -> SwapResult:
        # atomic: shadow → active, active → previous (kept until retire)
        # also rewrites index.json and Settings file (D8)
        ...

    def retire_generation(self, kb_name: str, generation: int, force: bool = False) -> None:
        # respects D4 24h window unless force=True
        ...
```

`current` is preserved as "the kb most recently swapped to" for legacy single-KB callers; not affected by shadow installation.

`get_kb` is the only entry point for read paths (`/retrieve`, `/search`); read paths NEVER touch shadow.

## 5. Shadow Build Runtime

Reuse existing `AppState.start_rebuild` infrastructure (`state.py:_rebuild_worker`, threading.Thread, RebuildTask). No asyncio introduction.

### 5.1 New entry point

```python
def start_shadow_rebuild(
    self,
    docs_dir: str | Path,
    kb_name: str,
    cfg: Settings,
    *,
    target_versions: TargetVersions,    # parser/chunker/embedder/index_schema versions for the shadow
    on_success=None,
) -> RebuildTask:
```

Differences from existing `start_rebuild`:

1. Acquires `lock_for(kb_name + ":shadow")` (separate lock from active rebuild lock — active incremental rebuild can run concurrently with shadow build per D7).
2. Builds an **ephemeral Settings clone** with `target_versions` overlaid; passes into `build_kb_incremental` so embedder/parser/chunker are instantiated for the new versions.
3. On success: writes artifacts to `{kb_root}/g{N+1}/...` and `{prefix}_{kb}_g{N+1}` Qdrant collection (NOT KB root or active collection); calls `install_shadow(kb_name, new_state)`; updates `index.json` to set `generations[N+1].status="ready"`, clears progress.
4. On failure: updates `index.json` to `status="failed"` with structured error; cleans up partial files in `g{N+1}/`; cancel-shadow API later removes the entry.
5. Progress updates: the build worker periodically writes `index.json.generations[N+1].progress` via atomic_write; granularity = embed-batch level (the embedding step dominates wall time).

### 5.2 Cancel semantics

`cancel_shadow_rebuild(kb_name)`:

1. Marks `RebuildTask.status="cancelled"` (existing `_raise_if_cancelled` poll points trigger).
2. Worker thread observes cancellation at the next poll, raises `RebuildCancelledError`, exits.
3. Cleanup: delete `{kb_root}/g{N+1}/` partial files; delete Qdrant collection `{prefix}_{kb}_g{N+1}` if created; clear `index.json.shadow_generation` and remove the `generations[N+1]` entry.
4. `cancel_shadow` is also valid against a `ready` shadow (un-promote without retire); same cleanup.

### 5.3 Crash recovery

On `AppState` startup, for each KB with `index.json.shadow_generation != null` AND `generations[shadow].status == "building"`:

1. Mark `generations[shadow].status="failed"`, set `error={"type":"OrphanedShadow","message":"process restarted during shadow build"}`.
2. Do not auto-cleanup files; require explicit `cancel-shadow` to delete (audit).

### 5.4 Concurrency rules

| Concurrent operation | Active read | Active incr. rebuild | Shadow build | Swap | Retire |
|---|---|---|---|---|---|
| Active read | OK | OK | OK | OK (read sees pre-swap state until swap completes) | OK if not retiring active |
| Active incr. rebuild | — | rejected (existing lock) | OK | rejected (swap waits for active rebuild lock) | OK |
| Shadow build | — | — | rejected (D3 409) | rejected (swap waits for shadow lock) | OK if not the shadow being built |
| Swap | — | — | — | rejected (lock) | sequential |
| Retire | — | — | — | — | rejected if same generation |

## 6. Admin API

All endpoints align with existing admin route style (`/admin/...`), use the same auth dependency as `/admin/manual-library` etc., return structured `ServiceError` shape on failure.

### 6.1 Endpoints

```
POST /admin/generation/build-shadow
  body: {
    "kb_name": "default",
    "embedding_model_id": "...",          // optional
    "embedding_model_version": "...",     // optional
    "parser_version": "...",              // optional
    "chunker_version": "...",             // optional
    "index_schema_version": int           // optional
  }
  200: { "kb_name": "default", "shadow_generation": 3, "task_id": "uuid" }
  400 NO_VERSION_DIFF: at least one version field must differ from active
  409 SHADOW_BUILD_IN_PROGRESS: { "shadow_generation": 3, "progress": 0.45 }

POST /admin/generation/cancel-shadow
  body: { "kb_name": "default" }
  200: { "cancelled_generation": 3 }
  404 NO_SHADOW: no shadow generation exists for this kb

POST /admin/generation/swap
  body: { "kb_name": "default" }
  200: { "previous_active": 2, "new_active": 3 }
  409 NO_READY_SHADOW: shadow does not exist or is not ready
  409 ACTIVE_REBUILD_IN_PROGRESS: active KB has a rebuild in progress (caller retries)

POST /admin/generation/retire
  body: { "kb_name": "default", "generation": 2, "force": false }
  200: { "retired_generation": 2 }
  400 RETIRE_ACTIVE: cannot retire the active generation
  400 RETIRE_SHADOW: cannot retire the shadow generation (use cancel-shadow)
  409 RETIRE_TOO_EARLY: { "retry_after_seconds": 81000 }
  404 NO_SUCH_GENERATION

GET /admin/generation/status?kb_name=default
  200: <full index.json contents for that kb>
  404 NO_SUCH_KB
```

### 6.2 Auth

All endpoints require admin scope (matching existing `/admin/manual-library` policy). No public exposure.

### 6.3 Error code registry additions

Added to `errors.py` ErrorCode enum:

- `INDEXGEN_NO_VERSION_DIFF`
- `INDEXGEN_SHADOW_BUILD_IN_PROGRESS`
- `INDEXGEN_NO_SHADOW`
- `INDEXGEN_NO_READY_SHADOW`
- `INDEXGEN_ACTIVE_REBUILD_IN_PROGRESS`
- `INDEXGEN_RETIRE_ACTIVE`
- `INDEXGEN_RETIRE_SHADOW`
- `INDEXGEN_RETIRE_TOO_EARLY`
- `INDEXGEN_NO_SUCH_GENERATION`
- `INDEXGEN_NO_SUCH_KB`
- `INDEXGEN_SETTINGS_META_MISMATCH` (startup check)

## 7. Settings ↔ index.json Sync (D8)

### 7.1 Read path on startup

```python
def validate_settings_against_meta(settings: Settings, meta: KbMeta) -> None:
    active = meta.generations[str(meta.active_generation)]
    mismatches = []
    if settings.parser.version != active["parser_version"]: mismatches.append("parser_version")
    if settings.chunker.version != active["chunker_version"]: mismatches.append("chunker_version")
    if settings.model.embedding_model_id != active["embedding_model_id"]: mismatches.append("embedding_model_id")
    if settings.model.embedding_model_version != active["embedding_model_version"]: mismatches.append("embedding_model_version")
    if settings.storage.index_schema_version != active["index_schema_version"]: mismatches.append("index_schema_version")
    if mismatches:
        raise ServiceError(
            ErrorCode.INDEXGEN_SETTINGS_META_MISMATCH,
            "Settings disagree with active generation. Operator must reconcile manually.",
            {"kb_name": meta.kb_name, "mismatches": mismatches,
             "settings_values": {...}, "meta_values": {...}}
        )
```

Called for each KB during startup (before serving traffic). Settings file path: `Settings.config_path` (existing convention).

### 7.2 Write path on swap

```python
def swap_generation(self, kb_name: str) -> SwapResult:
    # 1. Acquire active+shadow rebuild locks.
    # 2. Snapshot current index.json.
    # 3. Build new index.json: active → shadow value; previous active gets swap_at preserved (already set on initial build); shadow_generation → null.
    # 4. atomic_write(index.json, new_meta) — primary persistence point.
    # 5. Compute target Settings dict from new_meta.generations[new_active].
    # 6. atomic_write(Settings.config_path, new_settings_dict).
    # 7. Reload Settings into the running process (config.load_config from disk).
    # 8. Move shadow_kbs[kb] → kbs[kb]; clear shadow_kbs[kb].
    # 9. Release locks; clear query cache for this kb.
```

Failure handling:

- Step 4 fails (meta write): no state change, return error. Operator retries.
- Step 4 succeeds, Step 6 fails (settings write): index.json is the truth; old settings file remains; startup will detect mismatch on next restart and require manual fix. Log loud error. Continue serving on new active (read path uses index.json, not settings, for choosing generation).
- Step 6 succeeds, Step 7 fails (process reload): unlikely (in-process reload is local); if it does, log error and rely on next restart.
## 8. Migration Flow (D1)

Triggered lazily on `AppState` startup, per KB:

```python
def migrate_kb_to_g1_if_needed(kb_root: Path, settings: Settings) -> None:
    meta_path = kb_root / "index.json"
    if meta_path.exists():
        return  # already migrated; idempotent

    # Detect legacy layout
    legacy_files = ["graph.json", "vectors.npz", "chunk_identity.json", "epa_basis.npz",
                    "tag_embeddings.npz", "tag_cooccurrence.json", "tag_intrinsic_residuals.npz"]
    has_legacy = any((kb_root / f).exists() for f in legacy_files)
    if not has_legacy:
        # Empty KB; create index.json with no generations
        atomic_write(meta_path, lambda p: p.write_text(json.dumps({
            "schema_version": 1, "kb_name": kb_root.name,
            "active_generation": None, "shadow_generation": None, "generations": {}
        })))
        return

    # File-level migration
    g1_dir = kb_root / "g1"
    g1_dir.mkdir(parents=True, exist_ok=True)
    for f in legacy_files:
        src = kb_root / f
        if src.exists():
            os.rename(src, g1_dir / f)
    if (kb_root / "anchors").is_dir():
        os.rename(kb_root / "anchors", g1_dir / "anchors")

    # Qdrant alias (only if Qdrant backend configured)
    if settings.vector_store.provider == "qdrant":
        client = make_qdrant_client(settings)
        legacy_collection = collection_name_legacy(settings.qdrant.prefix, kb_root.name)  # "{prefix}_{kb}"
        new_collection = collection_name(settings.qdrant.prefix, kb_root.name, generation=1)  # "{prefix}_{kb}_g1"
        try:
            client.update_collection_aliases(change_aliases_operations=[
                {"create_alias": {"alias_name": new_collection, "collection_name": legacy_collection}}
            ])
        except qdrant_exceptions.AlreadyExists:
            pass  # idempotent

    # Write index.json with full snapshot of current Settings as the g1 entry
    g1_entry = {
        "created_at": _now(),
        "swap_at": _now(),
        "retired_at": None,
        "parser_version": settings.parser.version,
        "chunker_version": settings.chunker.version,
        "embedding_model_id": settings.model.embedding_model_id,
        "embedding_model_version": settings.model.embedding_model_version,
        "index_schema_version": settings.storage.index_schema_version,
        "chunk_count": _count_chunks_from_legacy_graph(g1_dir / "graph.json"),
        "build_id": _read_legacy_build_id(g1_dir / "graph.json")
    }
    meta = {"schema_version": 1, "kb_name": kb_root.name,
            "active_generation": 1, "shadow_generation": None,
            "generations": {"1": g1_entry}}
    atomic_write(meta_path, lambda p: p.write_text(json.dumps(meta, indent=2)))
```

Idempotency: re-running on a migrated KB exits at the first `if meta_path.exists()`.

Atomicity caveat: file moves are sequential (`os.rename` is per-file atomic but the set is not transactional). If process crashes mid-migration, on restart:
- Some files in `g1/`, some in root → migration code detects and resumes (each rename is independently idempotent because target exists check).
- Add resume logic: if `g1/` exists but `index.json` does not, finish the move + write meta. If `index.json` exists but some legacy files still in root (corruption), log error and abort startup.

## 9. Storage Backend Abstraction Updates (D5)

`storage/base.py` (existing vector-store interface) gains `generation` parameter on factory:

```python
def create_vector_store(settings: Settings, kb_name: str, generation: int) -> VectorStore: ...
```

NPZ implementation: paths interpolate generation; `npz_vector.py` reads/writes `{kb_root}/g{N}/vectors.npz` and parallel `vector_point_ids.npy`.

Qdrant implementation: `collection_name(prefix, kb, generation)` returns `{prefix}_{kb}_g{N}`; `_safe_collection_part` already handles sanitization.

Read paths (`/retrieve`, `/search`) get the active generation from `index.json` via AppState.generation_meta cache; never read from raw Settings for collection name resolution.

Shadow build paths get the shadow generation explicitly from `start_shadow_rebuild` argument.

## 10. Test Matrix

Unit tests:

- `test_chunk_identity::test_chunk_id_does_not_change_when_embedder_changes` — A1.a regression.
- `test_chunk_identity::test_vector_point_id_changes_with_embedder_version` — A1.b lock.
- `test_storage_state::test_collection_name_includes_generation` — naming function.
- `test_storage_state::test_meta_json_round_trip` — schema serialization.
- `test_state::test_install_shadow_does_not_affect_active_reads` — read isolation.
- `test_state::test_swap_generation_updates_meta_and_settings` — write atomicity.
- `test_state::test_swap_failure_settings_write_keeps_meta_truth` — partial-failure handling.
- `test_state::test_retire_too_early_returns_409` — D4 window check.
- `test_state::test_retire_force_bypasses_window` — D4 force.
- `test_state::test_orphaned_shadow_marked_failed_on_startup` — D3 crash recovery.
- `test_indexgen_migration::test_migration_creates_g1_layout` — D1 file move.
- `test_indexgen_migration::test_migration_idempotent` — D1 re-run.
- `test_indexgen_migration::test_migration_creates_qdrant_alias` — D1 alias (mocked client).

Integration tests:

- `test_indexgen_e2e::test_full_lifecycle_npz` — build → shadow build → swap → retire on NPZ backend.
- `test_indexgen_e2e::test_full_lifecycle_qdrant` — same on Qdrant backend (uses `FakeQdrantClient`).
- `test_indexgen_e2e::test_active_incremental_rebuild_during_shadow_build` — D7 concurrency.
- `test_indexgen_e2e::test_swap_back_before_retire` — rollback path.

API tests:

- `test_admin_generation_api::test_build_shadow_returns_409_on_concurrent` — D3.
- `test_admin_generation_api::test_status_returns_full_meta` — GET endpoint.
- `test_admin_generation_api::test_swap_clears_query_cache` — interaction with existing cache layer.

Eval slice (per architecture C9): replay current `search-feedback.jsonl` against shadow before swap; manually scripted in this task because T5 replay tool is separate. Acceptance: hit@5 on existing fixtures must not regress vs active.

## 11. Rollout & Rollback

**Rollout:** ship with feature behind no flag (the migration is idempotent and runs on startup; admin endpoints are dormant until called). Existing tests must continue to pass. Migration ran successfully on dev fixtures + one integration test KB before merge.

**Rollback:** revert the merge; the legacy collection name is still alive (alias points to it), legacy file paths can be restored from `g1/` by reverse rename.

**Compatibility:** existing `/retrieve` / `/search` / rebuild endpoints unchanged in behavior. New endpoints are additive.

## 12. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Settings file write fails after index.json swap | low | index.json is the truth source; startup check catches mismatch loudly |
| Qdrant alias not idempotent across versions | medium | catch AlreadyExists; verify on integration test |
| Active incremental rebuild + shadow build interfere through shared state | medium | separate locks (active vs shadow); separate target dirs; concurrency table |
| Shadow build progress writes corrupt index.json | low | atomic_write; progress is one field, write is small |
| Process crash during migration leaves half-moved files | low | idempotent migration with resume logic |
| Test coverage gaps | medium | explicit test matrix; eval slice replay before merge |

## 13. Dependencies on Other Tasks

- T2 (QueryPlan persistence) does NOT depend on this task to start design, but its implementation needs T1's `served_by_generation` field to be settable. Suggest T2 brainstorm runs in parallel; T2 implementation starts after T1 lands.
- T3 (Reranker), T6 (/answer), T7 (OCR), T8 (visual), T9 (connectors) all depend on T1 for safe rebuild semantics.
- T5 (replay tool) depends on T2; not affected by T1 directly.

## 14. Open Detail-Level Decisions Deferred to Implementation

- Exact JSON schema versioning: `schema_version: 1` with forward-only migration logic if v2 is ever needed.
- Whether `progress` field updates use atomic_write (heavier) or direct write with file lock (lighter) — chosen during implementation based on contention measurements.
- Maximum shadow build duration before auto-cancel — initial choice: no auto-cancel; operator monitors.
- Exact error message wording (i18n bandaid not in scope).
