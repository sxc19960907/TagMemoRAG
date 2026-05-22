# Directory Structure

> Backend module layout for TagMemoRAG.

---

## Overview

TagMemoRAG is a single Python package under `src/tagmemorag/`. Keep the M0 codebase small, explicit, and layer-oriented. The project is new, so these conventions come from the accepted M0 PRD/design rather than from legacy code.

The core rule is dependency direction: top-level entry points may call lower layers, but lower layers must not import API, CLI, or application state.

---

## Directory Layout

```text
src/tagmemorag/
├── __init__.py
├── __main__.py
├── types.py
├── config.py
├── parser.py
├── embedder.py
├── graph_builder.py
├── wave_searcher.py
├── anchor.py
├── state.py
├── api.py
├── cli.py
├── errors.py
└── storage/
    ├── __init__.py
    ├── base.py
    ├── atomic.py
    ├── json_graph.py
    ├── npz_vector.py
    └── json_anchor.py

tests/
├── fixtures/
├── unit/
└── e2e/
```

Runtime data belongs under `data/{kb}/` and must not be committed.

---

## Module Organization

Pure function layer:

- `parser.py`: Markdown/TXT chunking only. It returns `Chunk` objects and does not load models, write files, or access app state.
- `embedder.py`: wraps `sentence-transformers` encoding and normalization.
- `graph_builder.py`: builds a NetworkX graph from chunks and embeddings.
- `wave_searcher.py`: performs wave propagation search from explicit graph/vector/anchor inputs.

Stateful layer:

- `storage/*`: persistence abstractions and JSON/NPZ implementations.
- `anchor.py`: anchor CRUD and reconcile behavior.
- `state.py`: `AppState`, current graph reference, rebuild task registry, rebuild lock, and atomic swap.

Entry points:

- `api.py`: FastAPI request/response models, error handlers, and route wiring.
- `cli.py`: argparse commands for build, search, and serve.
- `__main__.py`: forwards `python -m tagmemorag` to `cli.main`.
- `cli_feedback.py`: feedback CLI command execution.
- `cli_helpers.py`: shared argparse/file helper functions used by CLI commands.
- `qa_context.py`: user QA short-context normalization and summary helpers.

Shared contracts:

- `types.py`: dataclasses such as `Chunk`, `Anchor`, `Result`, and `GraphState`.
- `config.py`: Pydantic settings and YAML loading.
- `errors.py`: service error codes and exceptions.

---

## Dependency Rules

- `parser`, `embedder`, `graph_builder`, and `wave_searcher` must not import `api`, `cli`, or `state`.
- `storage` modules must not import FastAPI or CLI code.
- `api.py` and `cli.py` may orchestrate lower layers through `AppState`, config, storage, and search/build helpers.
- If a helper is needed by multiple modules, prefer placing it in the narrowest shared module that owns the concept. Do not create a generic `utils.py` unless at least three modules genuinely share the same helper.

---

## Naming Conventions

- Use snake_case filenames and functions.
- Keep module names domain-specific: `graph_builder.py`, not `builder.py`; `wave_searcher.py`, not `search.py`.
- Use dataclass names for stable domain contracts: `Chunk`, `Anchor`, `Result`, `GraphState`.
- Use `kb_name` for knowledge-base identifiers. The default KB is `default`.
- Use `anchor_key` for stable anchor identity and `node_id` only for in-memory graph binding.
- Use `build_id` in search responses and logs to identify which graph version served a query.

---

## Examples

The canonical implementation order is documented in:

- `.trellis/tasks/05-10-wave-rag-implementation/design.md`
- `.trellis/tasks/05-10-wave-rag-implementation/implement.md`

When adding new M1-M4 features, preserve this M0 module boundary unless a new Trellis task explicitly changes the architecture.
