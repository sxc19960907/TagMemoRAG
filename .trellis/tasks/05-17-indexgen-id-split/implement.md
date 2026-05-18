# T1 — IndexGeneration mechanism + ID system split — Implementation Checklist

This task ships in tightly-scoped slices. Each slice is independently reviewable; commits roll up at slice boundaries.

## Pre-flight

- [ ] Confirm git tree clean on `feat/wave-phase1-cooccurrence-spike`.
- [ ] Confirm active task: `python3 ./.trellis/scripts/task.py current --source` returns this task.
- [ ] Re-read `prd.md` decisions D1–D8 and `design.md` § 1–14.
- [ ] Eval slice naming (per [[eval-as-driver-mechanism]]): document in this file before `task.py start`. Slice = "current `search-feedback.jsonl` rolling 100 entries replayed via ad-hoc script; hit@5 must not regress." If the jsonl is too small, fall back to `tests/fixtures/eval` fixtures.

## Slice 0 — Settings: add embedding_model_id/version + index_schema_version (prerequisite)

Discovered during Slice 1 prep: `ModelConfig` has `name` but no explicit `embedding_model_id` / `embedding_model_version`; `StorageConfig` already has `schema_version` we can repurpose as `index_schema_version`.

- [ ] Add to `ModelConfig` in `src/tagmemorag/config.py`:
  - `embedding_model_id: str | None = None` — when None, falls back to `name`. Lets v2 introduce explicit decoupling without breaking existing configs.
  - `embedding_model_version: str = "v1"` — default v1 for all existing deployments.
- [ ] Add helper accessors `Settings.model.effective_embedding_model_id` (returns `embedding_model_id or name`).
- [ ] Verify `StorageConfig.schema_version` is the field A4 trigger refers to; if so, alias it as `index_schema_version` semantically (no rename to keep diff small).
- [ ] Tests: `test_config_env.py` — defaults round-trip; explicit values round-trip.
- [ ] Commit: `feat(indexgen): add embedding_model_id/version fields to ModelConfig`.

## Slice 1 — chunk_id audit + vector_point_id derivation (A1, payload-only)

Scope contract: introduce the `vector_point_id` concept and lock `chunk_id` invariants. Do NOT yet replace Qdrant's int point id; storage backends keep using `node_id` as their key. Slice 1.5 (below) handles the type migration.

- [ ] Add `tests/unit/test_chunk_identity.py::test_chunk_id_does_not_change_when_embedder_changes` (must pass without code change to `chunk_identity.py`).
- [ ] Create `src/tagmemorag/vector_id.py` with `vector_point_id(chunk_id, embedding_model_id, embedding_model_version) -> str` (UUID-shaped, deterministic via SHA-256 → first 16 bytes → uuid.UUID).
- [ ] Add `tests/unit/test_vector_id.py::test_vector_point_id_changes_with_embedder_version` and `::test_vector_point_id_is_deterministic`.
- [ ] Add `vector_point_id` to `SAFE_QDRANT_PAYLOAD_KEYS` so it can be carried in payload.
- [ ] Wire `vector_point_id` computation into the Qdrant write path (`update`/`add`): when `chunk_id` is present in payload AND `embedding_model_id`+`version` are derivable from settings, write `vector_point_id` into payload alongside `node_id`. point id remains `int(node_id)` for now.
- [ ] Validation: `pytest tests/unit/test_chunk_identity.py tests/unit/test_vector_id.py tests/unit/test_storage_state.py`.
- [ ] Commit: `feat(indexgen): introduce vector_point_id derivation; add to Qdrant payload`.

## Slice 1.5 — REMOVED

Originally proposed: replace Qdrant point id with UUID-shaped `vector_point_id`. Removed during Slice 1 review with rationale documented in `design.md` § 3.2 and `architecture.md` § A1 "Storage role of vector_point_id":

- A4 collection-per-generation already isolates embedder versions; `node_id` is unambiguous within a collection.
- Type migration (UUID vs int) would churn every Qdrant call site without adding isolation.
- `vector_point_id` lives in the Qdrant payload (Slice 1) so cross-generation tools can match rows.

Skip ahead to Slice 2.

## Slice 2 — generation-aware naming + meta.json schema (D1, D2 partial)

- [ ] Extend `storage/qdrant_vector.py:collection_name(prefix, kb)` → `collection_name(prefix, kb, generation)`. Keep a thin shim returning legacy name when called without generation, used only by migration.
- [ ] Define `KbMeta` dataclass and JSON shape per design § 2.3 in new `src/tagmemorag/indexgen/meta.py`.
- [ ] Implement `read_meta(kb_root)` / `write_meta(kb_root, meta)` using existing `storage/atomic.atomic_write`.
- [ ] Add unit tests for round-trip serialization, schema_version handling, history_max trimming.
- [ ] Commit: `feat(indexgen): add KbMeta schema and atomic read/write`.

## Slice 3 — migration logic (D1)

- [ ] Implement `migrate_kb_to_g1_if_needed(kb_root, settings)` per design § 8.
- [ ] Add Qdrant alias creation (mocked test client first; real client behind import guard).
- [ ] Add resume logic for partial-migration.
- [ ] Unit tests: legacy → migrated; idempotent re-run; partial-state resume; alias creation; empty-kb path.
- [ ] Wire `migrate_kb_to_g1_if_needed` into `AppState` startup (one call per KB before any read).
- [ ] Validation: integration test reproducing legacy fixture → migration → first read.
- [ ] Commit: `feat(indexgen): migrate legacy KB layout to g1 (idempotent, resume-safe)`.

## Slice 4 — AppState dual-generation model (D2 cont., D3 partial)

- [ ] Add `shadow_kbs`, `generation_meta` fields to `AppState`.
- [ ] Implement `get_shadow_kb`, `install_shadow`, `swap_generation` skeletons (swap details in slice 6).
- [ ] Add startup orphan-shadow detection per design § 5.3; mark failed; log loud.
- [ ] Unit tests: install_shadow does not affect active reads; orphan shadow marked failed on startup.
- [ ] Commit: `feat(indexgen): add shadow generation slot to AppState`.

## Slice 5 — shadow build runtime (D3, D6, D7)

- [ ] Implement `start_shadow_rebuild` (separate lock `kb+":shadow"`).
- [ ] Build ephemeral Settings clone overlaid with `target_versions`.
- [ ] Direct `build_kb_incremental` output to `g{N+1}/` and Qdrant `_g{N+1}` collection.
- [ ] Persist all derivatives (tag embeddings, EPA basis, co-occurrence, residuals) into `g{N+1}/`.
- [ ] Periodic progress write to `meta.json.generations[N+1].progress`.
- [ ] Cancel via existing `_raise_if_cancelled` poll points; cleanup partial files + Qdrant collection.
- [ ] Concurrency: prove active incremental rebuild can run during shadow build (D7).
- [ ] Tests: shadow build success; cancel mid-build; second build-shadow returns 409; concurrent active incremental rebuild succeeds.
- [ ] Commit: `feat(indexgen): shadow rebuild path with cancel and progress`.

## Slice 6 — swap + retire + Settings sync (D4, D8)

- [ ] Implement `swap_generation` per design § 7.2 (atomic_write meta then settings; reload Settings).
- [ ] Implement `retire_generation` with D4 24h window check + force override.
- [ ] Add `INDEXGEN_*` ErrorCode enum entries.
- [ ] Tests: swap success; swap with shadow build still in progress rejected; retire too early rejected; retire force succeeds; partial swap failure (settings write fails) preserves meta truth.
- [ ] Commit: `feat(indexgen): swap and retire with Settings sync and safety window`.

## Slice 7 — admin API (D3 cont.)

- [ ] Add 5 endpoints under `src/tagmemorag/api.py` (or new `api_indexgen.py` module imported by main app):
  - `POST /admin/generation/build-shadow`
  - `POST /admin/generation/cancel-shadow`
  - `POST /admin/generation/swap`
  - `POST /admin/generation/retire`
  - `GET  /admin/generation/status`
- [ ] Wire admin auth dependency (matching `/admin/manual-library`).
- [ ] Map ServiceError → ErrorResponse for new codes.
- [ ] API tests for each endpoint: happy path + each error code.
- [ ] Commit: `feat(indexgen): admin API for shadow/swap/retire/status`.

## Slice 8 — Settings vs meta startup validation (D8 cont.)

- [ ] Implement `validate_settings_against_meta` per design § 7.1.
- [ ] Wire into AppState startup; raise `INDEXGEN_SETTINGS_META_MISMATCH` and refuse to serve if mismatch.
- [ ] Test: mismatched fixture → startup fails with structured error.
- [ ] Test: matching fixture → startup succeeds.
- [ ] Commit: `feat(indexgen): startup validation of Settings vs meta.json`.

## Slice 9 — eval slice replay (C9 obligation)

- [ ] Pick eval slice: rolling 100 entries from `search-feedback.jsonl` per loaded KB; if jsonl insufficient, use `tests/fixtures/eval` fixtures.
- [ ] Write a small ad-hoc script `scripts/replay_against_generation.py` (DO NOT block on T5 replay tool): reads jsonl/fixtures, replays each query against `meta.json.active_generation`, prints hit@5.
- [ ] Run shadow build with identical versions as active (control case): hit@5 must match active baseline (smoke proof of the mechanism).
- [ ] Document the result in this implement.md before reporting completion.
- [ ] Commit: `chore(indexgen): add eval-replay script for shadow validation`.

## Final Validation

```bash
# Existing test suite must pass
uv run pytest tests/unit tests/integration -x

# New error codes registered
grep -E 'INDEXGEN_' src/tagmemorag/errors.py | wc -l   # expect ≥ 11

# Admin API surface complete
grep -E 'generation/(build-shadow|cancel-shadow|swap|retire|status)' src/tagmemorag/api.py | wc -l   # expect ≥ 5

# Migration ran on at least one fixture
ls tests/fixtures/legacy_kb/g1/ 2>/dev/null   # post-test artifact

# Lint / type
uv run ruff check src tests
uv run mypy src/tagmemorag

# Git hygiene
git diff --check
```

All must pass. Eval slice deltas reported above. No `production-grade` self-label introduced (architecture C10 rule).

## Review Gates

- [ ] After Slice 3 (migration done): smoke-test on a legacy dev fixture before continuing.
- [ ] After Slice 6 (swap done): full unit + integration suite green.
- [ ] After Slice 9 (eval): user review before declaring task complete.

## Rollback Strategy

Each slice's commit is independently revertable. The migration in Slice 3 has a manual reverse: rename `g1/*` back to KB root and delete `meta.json` + Qdrant alias. Document the reverse procedure in a comment in `migrate_kb_to_g1_if_needed`.

## Out-of-Band Notes

- `T2` may begin design work in parallel; do not block T2 brainstorm on this task's completion.
- If shadow build runtime exposes a fundamental limitation in `build_kb_incremental` (e.g. global mutable state), surface it via [[trellis-update-spec]] rather than silently working around it.
