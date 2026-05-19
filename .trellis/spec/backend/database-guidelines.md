# Database Guidelines

> Persistence and storage conventions for TagMemoRAG.

---

## Overview

M0 does not use a relational database or ORM. The storage layer is file-backed and intentionally split by concern:

- `GraphStore`: graph metadata and topology.
- `VectorStore`: embedding vectors and vector search.
- `AnchorStore`: anchor CRUD and rebuild reconcile.

The MVP implementation uses JSON plus NPZ:

- `data/{kb}/graph.json`
- `data/{kb}/vectors.npz`
- `data/{kb}/anchors.json`
- `data/{kb}/meta.json`

Do not introduce SQLite, Postgres, pickle, Faiss, Qdrant, or pgvector in M0 unless a new task changes scope. The base interfaces should leave room for those later.

---

## Storage Contracts

`storage/base.py` owns the abstract interfaces:

- `GraphStore.save(graph)` and `GraphStore.load()`.
- `VectorStore.add(ids, vecs)`, `VectorStore.search(query_vec, k)`, and `VectorStore.get(id)`.
- `AnchorStore` CRUD plus reconcile.

Incremental methods such as `add_nodes`, `remove_nodes`, `delete`, and `update` should exist as signatures and raise `NotImplementedError` in M0.

---

## Write Patterns

- All persisted files must be written with `write-to-temp + os.replace`.
- Never partially overwrite `graph.json`, `vectors.npz`, `anchors.json`, or `meta.json`.
- Save graph metadata separately from vectors. Do not store embeddings inside NetworkX node attributes.
- Include schema metadata in `meta.json`: `schema_version`, `model_name`, `model_dim`, `built_at`, and `chunk_count`.
- Refuse to load unknown or incompatible `schema_version` values instead of guessing.

---

## Query Patterns

- M0 vector search is exact numpy dot-product search over normalized vectors.
- `VectorStore.search(query_vec, k)` is the abstraction boundary for future Faiss/Qdrant/pgvector backends.
- Keep search inputs explicit. Do not hide query embedding, graph lookup, or anchor lookup inside the vector store.
- Search result ordering should be deterministic for equal scores by using a stable tie-breaker such as node id.
- When query-time ANN preselection is enabled for Qdrant, treat it as candidate generation only. Final search ranking must remain local and deterministic over the loaded graph and vectors unless a future task explicitly changes the ranking contract.

---

## Naming Conventions

- Runtime root: `data/`.
- Knowledge-base directory: `data/{kb_name}/`.
- Default knowledge base: `data/default/`.
- Graph file: `graph.json`.
- Vector file: `vectors.npz`.
- Anchor file: `anchors.json`.
- Metadata file: `meta.json`.

## Scenario: Managed Manual Library

### 1. Scope / Trigger

- Trigger: M6 file-backed manual management through API upload/update/delete and library-aware rebuild.
- The managed manual library is source working state. The loaded `GraphState` remains the serving artifact until rebuild succeeds.

### 2. Signatures

- Config: `Settings.manual_library.root_dir: str = "product_manuals"` and `allow_overwrite: bool = False`.
- Storage module: `manual_library.py` owns library root resolution, metadata validation, source/sidecar writes, manifest pending state, and listing.
- API signatures:
  - `POST /manuals/validate`
  - `POST /manuals` multipart: `kb_name`, `metadata`, `file`, `overwrite`, `trigger_rebuild`
  - `PATCH /manuals/{manual_id}/metadata`
  - `PUT /manuals/{manual_id}/file`
  - `DELETE /manuals/{manual_id}?kb_name=...&hard=false`
  - `GET /manual-library?kb_name=...&manual_id=...`
  - `POST /manual-library/rebuild`

### 3. Contracts

- Managed files live under `{manual_library.root_dir}/{kb_name}/`.
- Each source document uses the M5 sidecar format: `<stem>.metadata.json`.
- Per-KB manifest is `.tagmemorag-library.json` with `schema_version`, `kb_name`, `pending_changes`, `last_successful_build_id`, and `updated_at`.
- Incremental rebuild dirty state also lives in `.tagmemorag-library.json` under `dirty_manuals`, keyed by `manual_id` with `source_file`, `operation`, `updated_at`, and `checksum`. Older manifests without `dirty_manuals` remain loadable; if `pending_changes=true` and no dirty state exists, incremental rebuild must fall back to full rebuild with `fallback_reason=missing_dirty_state`.
- Successful managed-library rebuilds may write `data/{kb_name}/chunk_identity.json` and `data/{kb_name}/rebuild_impact.json`. The identity map is a built artifact with `schema_version`, `kb_name`, `build_id`, parser settings, stable chunk identity keys, text hashes, node ids, vector rows, and metadata hashes. The impact report is operational metadata with counts and hashes/ids only; it must not include raw chunk text.
- When `vector_store.provider=qdrant`, new points store safe payload fields only: `kb_name`, `node_id`, `build_id`, `chunk_identity_key`, `manual_id`, `source_file`, and `text_hash`. Raw chunk text, secrets, and embedding arrays outside the Qdrant vector itself must not be payload fields. Older Qdrant collections that only have `kb_name` and `node_id` payloads remain load-compatible.
- `source_file` must be relative, non-empty, path traversal free, and resolve under the KB library root.
- Supported source suffixes remain `.md`, `.txt`, and `.pdf`.
- Write sidecars and manifests with `atomic_write()`. Uploaded source files must replace through a temp file in the target directory.
- Metadata/status truth lives in sidecars. Manifest tracks only KB-level pending/build state.
- `status=disabled` and `status=archived` manuals stay listed but are skipped by `build_kb()`.
- Mutation endpoints mark the manifest pending. Only successful library rebuild clears pending and records `last_successful_build_id`.
- Managed library rebuilds support `mode=full|incremental|auto`. Full remains the compatibility default. Incremental rebuilds may reuse unchanged chunks/vectors but must rebuild final graph topology globally, save full graph/vector artifacts, swap only after save succeeds, and clear dirty state only in the success callback.
- Qdrant-backed managed-library rebuilds must sync Qdrant before saving the new graph/meta artifacts. Full sync upserts all current node ids and then deletes explicit stale old node ids. Safe point-incremental sync may skip unchanged node ids only when compatible chunk identity data proves the same node id, text hash, and metadata hash; otherwise it must fall back to full sync with a structured `fallback_reason`. Stale deletes must run only after required current upserts succeed. Failed Qdrant sync must preserve the old `GraphState` and leave dirty state pending.
- Qdrant sync summaries are additive metadata on rebuild tasks and persisted meta/impact artifacts: `provider`, `strategy`, `points_upserted`, `points_deleted`, `points_reused`, and `fallback_reason`.

### 4. Validation & Error Matrix

- Unsafe `source_file` -> `INVALID_INPUT`.
- Unsupported suffix -> `INVALID_INPUT`.
- Malformed metadata JSON/form field -> `INVALID_INPUT`.
- Duplicate `manual_id` during create validation -> validation message `DUPLICATE_MANUAL_ID`.
- Duplicate create/upload without overwrite -> `INVALID_REQUEST`.
- Unknown manual id for update/delete -> `INVALID_REQUEST`.
- Concurrent rebuild -> `REBUILD_IN_PROGRESS`.
- Missing scope or KB allowlist access -> `FORBIDDEN`.
- Hard delete without `admin` -> `FORBIDDEN`.
- Failed library rebuild leaves `pending_changes=true` and preserves the old `GraphState`.

### 5. Good/Base/Bad Cases

- Good: upload source + valid sidecar, list shows `rebuild_required=true`, library rebuild succeeds, list shows `searchable=true` and pending clears.
- Base: a KB with regular filesystem sidecars can still be built directly through CLI or `POST /rebuild`.
- Bad: writing a source file outside the library root, accepting `.exe`, or clearing pending before rebuild success.

### 6. Tests Required

- Unit: safe path traversal, unsupported suffix, metadata normalization, duplicate manual id, manifest pending, create/update/delete/list.
- Build: disabled sidecar is skipped while no-sidecar fallback remains active.
- API: validate, upload conflict, metadata update, soft delete, hard delete admin requirement, library listing, library rebuild.
- Regression: existing graph-derived `GET /manuals` and explicit `POST /rebuild {docs_dir}` stay compatible.
- Failure: failed library rebuild preserves old `GraphState` and keeps pending true.

### 7. Wrong vs Correct

#### Wrong

```python
target = Path(root) / request.metadata["source_file"]
target.write_bytes(await file.read())
```

This trusts client path text and can write outside the library root or expose a source file before a valid sidecar exists.

#### Correct

```python
target = safe_source_path(kb_name, metadata.source_file, settings)
_write_metadata(metadata_sidecar_path(target), metadata)
os.replace(tmp_upload_path, target)
```

Resolve and verify the path under the KB root, write metadata atomically, then replace the uploaded source in the target directory.

## Scenario: S3-Compatible Manual Blob Store

### 1. Scope / Trigger

- Trigger: M27 adds `manual_library.blob_backend=s3` as an optional object-storage backend behind `ManualBlobStore`.
- The registry remains the source of truth. S3 stores only original uploaded bytes and safe object metadata.

### 2. Signatures

- Config: `manual_library.blob_backend: local | s3`, `s3_bucket`, `s3_prefix`, `s3_endpoint_url`, `s3_region`, `s3_access_key_env`, `s3_secret_key_env`, `s3_session_token_env`, `s3_addressing_style`, `s3_timeout_seconds`.
- Factory: `create_blob_store(cfg) -> ManualBlobStore`.
- Store: `S3ManualBlobStore.put(kb_name, manual_id, source_file, content, metadata) -> BlobRef`, plus `get(blob_key)`, `exists(blob_key)`, and `delete(blob_key)`.
- Dependency: S3 support is optional via the `s3` extra; default local mode must not require boto3.

### 3. Contracts

- Object keys are safe relative keys: `{normalized_prefix}/{safe_kb_name}/{safe_manual_id}/{version}/{sha256-prefix}-{safe_basename}`.
- Registry rows store `blob_backend="s3"` and the object key only. Bucket, endpoint, and credentials stay in runtime config/env.
- Credentials are read from environment variables named by config. If access/secret env names are blank, allow boto3's default credential chain.
- Object metadata may include checksum, manual id, source filename basename, content type, and version. It must not include document text, raw paths, or secrets.
- Registry-backed migration, verify, upload, replace, delete, and rebuild use the same `ManualBlobStore` interface as local blob storage.

### 4. Validation & Error Matrix

- Missing `s3_bucket` -> `INVALID_CONFIG`.
- Missing optional boto3 dependency when `blob_backend=s3` -> `INVALID_CONFIG` with `{"dependency":"boto3","extra":"s3"}`.
- Named credential env var is unset -> `INVALID_CONFIG` with only the env var name.
- Unsafe blob key -> `INVALID_INPUT`.
- Missing object during `get()` -> `STORAGE_LOAD_FAILED`.
- S3 client failure during put/get/head/delete -> `STORAGE_LOAD_FAILED` with safe fields: backend, bucket, blob key, operation, and provider error code.

### 5. Good/Base/Bad Cases

- Good: registry upload writes the object first, then commits the registry row, then marks dirty.
- Base: `blob_backend=local` remains the default and all default tests run without boto3, MinIO, network, or credentials.
- Bad: returning or logging signed URLs, request headers, raw credential values, raw document bodies, absolute source paths, or object-store stack traces.

### 6. Tests Required

- Unit: prefix normalization, key safety, put/get/exists/delete, content type, size, checksum, metadata.
- Unit: missing bucket, missing dependency, missing credential env, unsafe key, missing object.
- Integration-style unit with fake client: S3-backed registry upload, replacement, sidecar migration, verify-blobs, and registry-backed rebuild.
- Failure: upload failure does not create a registry row or dirty state; missing object during rebuild preserves old `GraphState` and leaves dirty state pending.
- Env: `TAGMEMORAG__MANUAL_LIBRARY__S3_*` overrides load through `Settings`.

### 7. Wrong vs Correct

#### Wrong

```python
record.blob_key = f"s3://{bucket}/{key}?X-Amz-Signature=..."
```

This leaks deployment-specific URLs and may expose credential-bearing signed query parameters.

#### Correct

```python
blob_ref = blob_store.put(kb_name, manual_id, source_file, content, {"version": next_version})
registry.upsert(kb_name, metadata, blob_ref, operation="upsert")
```

Keep object storage behind `ManualBlobStore`, store only the safe object key in the registry, and commit registry state only after the object write succeeds.

## Scenario: Tag Intrinsic Residuals

### 1. Scope / Trigger

- Trigger: Phase 3.5 activates `tag_intrinsic_residuals` as a rebuild-produced registry table consumed by tag spike and ResidualPyramid.
- Applies when changing tag rebuild, cooccurrence, pyramid candidate ranking, or online tag boost residual handling.

### 2. Signatures

- Config: `wave_phase1.intrinsic_residuals_enabled: bool = False`, `wave_phase1.intrinsic_residual_top_n: int | None = None`.
- Trainer: `train_intrinsic_residuals_for_kb(kb_name, conn, matrix, expected_dim, top_n) -> IntrinsicResidualTrainReport`.
- CLI: `python -m tagmemorag retrain-residuals --kb=<name> --config=<path>`.
- DB: `tag_intrinsic_residuals(tag_id PRIMARY KEY, residual_energy REAL, neighbor_count INTEGER, computed_at TEXT)`.

### 3. Contracts

- Producer runs after cooccurrence rebuild when `wave_phase1.enabled` and `cooccurrence_enabled` are true, regardless of `intrinsic_residuals_enabled`.
- Consumer is gated only by `intrinsic_residuals_enabled`; default false must preserve baseline search behavior.
- Neighbor basis for tag T is cooccurrence outgoing plus incoming neighbors, ordered by max bidirectional weight desc then tag id asc, limited by `intrinsic_residual_top_n` or `pyramid_top_k`.
- Stored formula is `||T - projection(T, neighbor_basis)||^2 / ||T||^2`, clamped to `[0, 1]`; no usable basis or zero vector stores `1.0`.
- Missing online residual rows fall back to `1.0`.

### 4. Validation & Error Matrix

- Missing cooccurrence matrix in CLI -> exit code 2 with a concise stderr error.
- Trainer exception during rebuild -> fail-soft: graph rebuild continues and `tag_intrinsic_residual_error` records the exception type.
- Trainer exception during CLI -> exit code 2; do not hide the failure as success.

### 5. Good/Base/Bad Cases

- Good: rebuild writes cooccurrence, trains residual rows, and meta includes `tag_intrinsic_residual_rows`.
- Base: `intrinsic_residuals_enabled=false` still writes rows but online spike and pyramid behavior remain unchanged.
- Bad: making residual training block graph rebuild, or enabling consumers by default.

### 6. Tests Required

- Unit: residual formula, incoming+outgoing Top-N selection, no-basis fallback.
- Rebuild: rows written on success; trainer failure does not fail rebuild and records error type.
- CLI: `retrain-residuals` reports row counts and returns non-zero for missing inputs.
- Online: enabled-on passes residuals to spike and pyramid; default-off baseline invariance remains green.

### 7. Wrong vs Correct

#### Wrong

```python
residual = residuals[tag_id]
```

This turns partially trained or newly created tags into search-time failures.

#### Correct

```python
residual = residuals.get(tag_id, 1.0)
```

Fallback preserves compatibility while metrics expose missing training coverage.

---

## Phase 4 — V8 geodesicRerank

### 1. Scope / Trigger

- Trigger: Phase 4 ports VCPToolBox V8 `TagMemoEngine.geodesicRerank` so wave_search candidates are reranked by mean tag energy from Phase 1 spike.
- Applies when changing wave_search, search_runtime, TagBoostInfo shape, spike output, or any candidate-pool plumbing.

### 2. Signatures

- Config: `wave_phase1.geodesic_rerank_enabled: bool = False`, `wave_phase1.geodesic_alpha: float = 0.3` (clamped to `[0, 1]`), `wave_phase1.geodesic_oversample_factor: float = 2.0` (≥ 1.0), `wave_phase1.geodesic_min_geo_samples: int = 2` (≥ 1).
- Algorithm: `geodesic_rerank(candidates, *, energy_field, graph, kb_name, settings, top_k, alpha=None, min_geo_samples=None) -> GeodesicRerankResult`.
- Pool plumbing: `wave_search(..., rerank_pool_size: int | None = None)`. None ⇒ existing top_k truncation; non-None ⇒ pool returned for caller-side rerank.
- Spike transport: `TagBoostInfo.accumulated_energy: Mapping[int, float] | None`. Filled on spike-success path; None on every `skipped_reason` early return.

### 3. Contracts

- Hard dependency: V8 runs only when `phase1.enabled && phase1.spike_enabled && geodesic_rerank_enabled && boost_info.skipped_reason == "" && bool(boost_info.accumulated_energy)`. All other paths silent-noop.
- L0 (`energy_field` empty) / L1 (`hits < min_geo_samples`) / L2 (`max_geo == 0`) all preserve input order verbatim with classified `skipped_reason`.
- chunk → tag_id resolution reuses `metadata_from_node(graph.nodes[node_id])["tags"]` + `tag_store.lookup_tag_id`. No new schema or persistence table is introduced.
- Skipped-reason whitelist (fixed cardinality): `spike_disabled / matrix_missing / no_tag_vectors / no_seeds / no_candidates / degenerate_context / zero_alpha / degenerate_fused / energy_field_empty / max_geo_zero / lexical_only_path / unknown`.
- Default-off path is byte-equivalent to baseline (8 hashing eval suites + e2e baseline invariance must stay green).

### 4. Validation & Error Matrix

- Settings validation: `geodesic_alpha ∈ [0, 1]`, `geodesic_oversample_factor ≥ 1.0`, `geodesic_min_geo_samples ≥ 1` enforced via pydantic `Field`. Out-of-range values raise `ValidationError` at load time.
- V8 internal exceptions never propagate; the algorithm catches and returns `GeodesicRerankResult(skipped_reason="unknown", applied=False)`.
- `record_geodesic_rerank_swap` drops unrecognized `kind` labels silently; `record_geodesic_rerank_skipped` clamps unknown reasons to `"unknown"`.

### 5. Good/Base/Bad Cases

- Good: flag-on + spike-success + non-empty energy field + at least one candidate has tags ⇒ `applied=True`, swap_total / hit_count_observed metrics populated.
- Base: flag-off ⇒ `wave_search(rerank_pool_size=None)`, no metric registration, byte-equivalent to baseline.
- Bad: introducing implicit cache for `accumulated_energy` outside of `TagBoostInfo`; mutating input candidates; bypassing `metadata_from_node` to read `chunk.tags` directly (fragile across legacy node shape variants); recording a non-whitelisted reason or kind.

### 6. Tests Required

- Unit: three-layer fallback (L0/L1/L2), α=0/1 extremes, swap classification, diagnostic fields on `Result.metadata`, input not mutated, unknown tags silently dropped.
- Integration: flag-off byte equivalence (e2e baseline invariance), flag-on + spike-off skip metric, flag-on + spike-success applied path, filter-strict pool < pool_size.
- Lexical compat: V8 reads `metadata.tags` regardless of candidate provenance; hybrid pool (lexical + ANN) classifies swap kinds correctly.
- Diag: `scripts/diag_geodesic_rerank.py` reports `applied_pct > 0` and `max_geo_zero_pct < 50` on the product-manual fixture set.

### 7. Wrong vs Correct

#### Wrong

```python
energy = some_module.GLOBAL_ENERGY_CACHE[kb_name]   # implicit side channel
results = wave_search(...)                          # no oversampling
reranked = geodesic_rerank(results, energy_field=energy, ...)
```

Implicit globals leak across requests and break determinism; reranking the
already-truncated top_k can only swap positions inside that slice and
cannot promote a high-energy candidate from the pool tail.

#### Correct

```python
boost_info = apply_tag_boost(...)                   # populates info.accumulated_energy
pool = max(top_k, ceil(top_k * factor)) if v8_should_run else None
results = wave_search(..., rerank_pool_size=pool)
if v8_should_run:
    reranked = geodesic_rerank(
        results, energy_field=boost_info.accumulated_energy, ..., top_k=top_k,
    )
    results = list(reranked.candidates[:top_k])
```

The energy field rides on `TagBoostInfo` (explicit data flow); oversampling
gives V8 a chance to pull genuinely better candidates into top_k.

---

## Common Mistakes

- Do not use pickle for graph persistence. It is brittle across versions and unsafe to deserialize from untrusted sources.
- Do not combine graph metadata and embeddings in one file.
- Do not silently rebuild a corrupted or mismatched KB on load; raise a clear service error.
- Do not make the API depend on concrete JSON/NPZ classes directly. Route through the storage interfaces or AppState orchestration.
- Do not clear the managed library pending marker when a rebuild task is merely accepted; clear it only inside the rebuild success path after graph swap.
