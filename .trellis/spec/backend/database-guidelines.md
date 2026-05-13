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

---

## Common Mistakes

- Do not use pickle for graph persistence. It is brittle across versions and unsafe to deserialize from untrusted sources.
- Do not combine graph metadata and embeddings in one file.
- Do not silently rebuild a corrupted or mismatched KB on load; raise a clear service error.
- Do not make the API depend on concrete JSON/NPZ classes directly. Route through the storage interfaces or AppState orchestration.
- Do not clear the managed library pending marker when a rebuild task is merely accepted; clear it only inside the rebuild success path after graph swap.
