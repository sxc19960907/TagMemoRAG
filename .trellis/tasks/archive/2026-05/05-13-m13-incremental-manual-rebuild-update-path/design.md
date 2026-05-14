# design.md - M13 Incremental Manual Rebuild/Update Path

## Scope

M13 adds an incremental managed-library rebuild path. The feature lives around `manual_library.py`, `state.py`, graph/vector persistence, API/CLI rebuild controls, and the manual library admin UI. It should not alter search ranking, eval semantics, auth policy, or the existing full rebuild endpoint for arbitrary `docs_dir`.

The recommended MVP optimizes parse/embed work while preserving the current final artifact shape:

```text
dirty manual set + old GraphState
  -> parse/embed only dirty active manuals
  -> reuse unchanged chunks/vectors from old state
  -> rebuild final graph edges globally
  -> save full graph + full vector matrix
  -> swap GraphState after success
```

This is less risky than introducing partial graph persistence or node-level Qdrant mutation in the same milestone.

## Current State

```text
manual_library mutation
  -> mark_pending(kb_name, pending=True)

POST /manual-library/rebuild
  -> start_library_rebuild()
  -> AppState.start_rebuild()
  -> build_kb(library_root, kb_name, cfg, old_state=...)
  -> save_kb()
  -> swap_kb()
  -> clear_pending_after_success()
```

Important files:

- `src/tagmemorag/state.py`: full build/load/save, rebuild tasks, async worker, library rebuild helper.
- `src/tagmemorag/manual_library.py`: managed source/sidecar mutations, manifest pending state, listing.
- `src/tagmemorag/graph_builder.py`: graph construction from chunks and embeddings.
- `src/tagmemorag/storage/npz_vector.py`: full NPZ vector save/load/search.
- `src/tagmemorag/storage/qdrant_vector.py`: Qdrant vector save/load/search by node ID.
- `src/tagmemorag/storage/json_graph.py`: full graph JSON save/load.
- `src/tagmemorag/api.py`: manual-library rebuild endpoint and admin route.
- `src/tagmemorag/cli.py`: build/search/eval/manual-bulk/tag/feedback command patterns.

## Proposed Module Boundary

Add `src/tagmemorag/incremental_rebuild.py`.

Responsibilities:

- Define dirty-manual journal dataclasses and serialization helpers.
- Update and clear dirty state under the managed library root.
- Build an incremental plan from dirty state, library records, and old `GraphState`.
- Convert reusable graph nodes back into `Chunk`-like build inputs or a narrow internal `BuildChunk` contract.
- Parse/embed only dirty active manuals.
- Assemble final chunks and vectors in deterministic order.
- Invoke existing `build_graph()` and anchor reconciliation.
- Return a `GraphState` plus rebuild metadata (`effective_mode`, counts, fallback reason).

Keep this module independent of FastAPI and CLI argument parsing. `manual_library.py` records dirty state; `state.py` orchestrates rebuild workers; API/CLI expose mode controls.

## Dirty State Contract

Recommended manifest extension:

```json
{
  "schema_version": "1",
  "kb_name": "default",
  "pending_changes": true,
  "last_successful_build_id": "202605...",
  "updated_at": "...",
  "dirty_manuals": {
    "coffee-machine": {
      "manual_id": "coffee-machine",
      "source_file": "coffee_machine.md",
      "operation": "file_replace",
      "updated_at": "...",
      "checksum": "..."
    }
  }
}
```

Alternative if keeping manifest small is preferable: `.tagmemorag-library-dirty.json`.

Recommended MVP: extend the existing manifest because there is already one per KB, it is atomically written, and older code can ignore unknown fields.

Rules:

- `mark_pending()` should accept optional dirty manual metadata.
- Every mutation in `manual_library.py` should record dirty info:
  - `upsert_manual`: new/updated manual ID and source path.
  - `update_manual_metadata`: old and new source path if moved; manual ID.
  - `replace_manual_file`: manual ID and source path.
  - `disable_manual`: manual ID and source path, operation `disable` or `archive`.
  - `delete_manual`: manual ID, old source path, operation `hard_delete`.
  - bulk import should record each imported/updated row.
- Multiple mutations to the same manual collapse into one dirty entry with the newest operation and timestamp.
- If old manifests lack `dirty_manuals` but `pending_changes=true`, incremental rebuild should fall back to full rebuild with reason `missing_dirty_state`.

## Build Contracts

### Reusable Node Extraction

For unchanged manuals, derive reusable build inputs from old graph nodes:

```python
@dataclass(frozen=True)
class ReusableChunk:
    node_id: int
    text: str
    header: str
    path: tuple[str, ...]
    level: int
    start_line: int
    source_file: str
    metadata: dict[str, Any]
    vector: np.ndarray
```

The reusable chunk must carry enough fields to call `build_graph()` after converting to `Chunk`.

Validation:

- Node metadata must contain `manual_id`.
- Node must have a matching vector row.
- Manual must still exist and be active in current library records.
- Optional metadata checksum/source file should match when available.

If reusable extraction fails for any unchanged manual, fall back to full rebuild.

### Dirty Manual Parsing

For dirty active manuals:

- Use `load_manual_metadata()` and `parse_document()` exactly like `build_kb()`.
- Embed dirty chunk text with `embedder.encode_batch()`.
- Preserve existing metadata normalization and inactive-status skip behavior.

For dirty inactive/deleted manuals:

- Do not parse or embed.
- Exclude old chunks for those manual IDs from final inputs.

### Deterministic Ordering

Final chunks should be ordered deterministically, ideally by `(source_file, start_line, header, text hash)`, matching or closely approximating full build order from sorted document paths.

Why this matters:

- Node IDs are rebuild-local but tests and vector rows rely on deterministic node ID order.
- Anchor reconciliation and eval reports are easier to compare.

### Graph Rebuild

Even in incremental mode, call `build_graph(final_chunks, final_vectors, cfg.graph)` on the complete final chunk set.

Reason:

- Semantic similarity edges can connect dirty and unchanged chunks.
- Parent/sibling/consecutive edges depend on final ordering and chunk paths.
- This preserves full-build WAVE-RAG behavior while avoiding unchanged embedding work.

## State and Task Metadata

Extend `RebuildTask`:

```python
requested_mode: str = "full"
effective_mode: str = "full"
dirty_manual_count: int = 0
fallback_reason: str = ""
reused_chunk_count: int = 0
embedded_chunk_count: int = 0
```

If changing the dataclass is too broad, add a `detail: dict[str, Any]` field and include these keys in `to_dict()`.

Recommended rebuild modes:

- `full`: current behavior.
- `incremental`: attempt incremental, fall back to full unless `allow_fallback=false`.
- `auto`: optional alias that chooses incremental when dirty state exists and full otherwise.

## API Design

Extend `ManualLibraryRebuildRequest`:

```python
class ManualLibraryRebuildRequest(BaseModel):
    kb_name: str = "default"
    mode: Literal["full", "incremental", "auto"] = "full"
    allow_fallback: bool = True
```

Endpoint:

```text
POST /manual-library/rebuild
```

Response remains a rebuild task dictionary with additional metadata.

Auth remains `rebuild` scope plus KB allowlist.

The legacy `POST /rebuild` endpoint remains full rebuild only.

## CLI Design

Add a managed-library rebuild helper if one does not exist yet:

```bash
python -m tagmemorag manual-library rebuild --kb default --mode incremental
python -m tagmemorag manual-library list --kb default
```

If adding a new command group feels too large, at minimum document API use and add tests around the API. Recommended MVP includes the rebuild CLI because M13 is operational.

CLI output should be JSON.

## Admin UI Design

Extend `/admin/manual-library`:

- Rebuild controls include a segmented/select control for `full`, `incremental`, and optional `auto`.
- The status area shows pending and dirty counts from `GET /manual-library`.
- Detail panel or table can show dirty status per manual if available.
- Rebuild polling displays requested/effective mode and fallback reason from task response.

Keep all controls in the existing dense operational shell.

## Cache and Persistence

Current query cache keys include `build_id`; after graph swap, new searches naturally use a different key. M13 should still clear or mark cache entries for the KB on successful rebuild if existing full rebuild behavior does that elsewhere. If current full rebuild does not clear cache, confirm the build-id key behavior in tests and preserve it.

Persistence remains:

```text
data/{kb}/graph.json
data/{kb}/vectors.npz or Qdrant collection
data/{kb}/anchors.json
data/{kb}/meta.json
```

Add meta fields:

```json
{
  "rebuild_mode": "incremental",
  "reused_chunk_count": 1200,
  "embedded_chunk_count": 7,
  "dirty_manual_count": 2,
  "fallback_reason": ""
}
```

## Fallback Rules

Fall back to full rebuild when:

- No old `GraphState` is loaded or loadable.
- Manifest has `pending_changes=true` but no dirty state.
- Dirty state references unknown/manual-id-conflicting records.
- Old graph nodes lack required chunk fields.
- Vector store cannot load vectors for old node IDs.
- Model dimension or schema version differs.
- Incremental comparison assertions fail in a debug/test-only path.

If `allow_fallback=false`, return a structured `INVALID_REQUEST` or rebuild task failure instead of full rebuilding.

## Rollout / Rollback

Rollout:

1. Ship dirty tracking with full rebuild still default.
2. Add incremental service and tests.
3. Expose API/CLI mode.
4. Add admin UI controls and docs.
5. Consider changing default from `full` to `auto` only after field confidence.

Rollback:

- Operators can continue using `mode=full`.
- Dirty manifest fields can be ignored by older code.
- If incremental service fails, fallback full rebuild preserves availability.

## Risks

- **Graph equivalence risk**: partial edge updates can miss cross-manual semantic edges. Mitigation: rebuild final graph globally.
- **Node ID drift**: any rebuild can change node IDs. Mitigation: stable identity remains anchor keys/source metadata; tests should not assume fixed IDs.
- **Qdrant stale vectors**: full final vector save/upsert may leave stale points if old IDs disappear. MVP should either delete/recreate collection safely or ensure load uses graph node IDs only. Add tests.
- **Dirty state drift**: mutation succeeds but dirty write fails. Mitigation: write source/sidecar and dirty manifest atomically enough, or fail mutation before reporting success.
