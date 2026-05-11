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

---

## Common Mistakes

- Do not use pickle for graph persistence. It is brittle across versions and unsafe to deserialize from untrusted sources.
- Do not combine graph metadata and embeddings in one file.
- Do not silently rebuild a corrupted or mismatched KB on load; raise a clear service error.
- Do not make the API depend on concrete JSON/NPZ classes directly. Route through the storage interfaces or AppState orchestration.
