# TagMemoRAG

A production-grade semantic retrieval engine for product manuals, built on the **WAVE-RAG** algorithm: knowledge chunks are organized into a semantic topology graph, and user queries propagate as waves along graph edges — interference peaks become the top-K results.

> **M0 scope note**: `kb_name` is reserved in the API/CLI but only `"default"` is supported. Multi-KB isolation lands in M2; passing any other value returns `404 KB_NOT_LOADED`.

## Install

```bash
# with uv (recommended)
uv sync --extra dev

# or pip
pip install -e ".[dev]"
```

## Quick Start

### 1. Build a knowledge base

```bash
python -m tagmemorag build --docs docs/ --kb default --config config.yaml
```

### 2. Search from CLI

```bash
python -m tagmemorag search "蒸汽很小" --kb default --top-k 5
```

### 3. Start the API server

```bash
python -m tagmemorag serve --host 127.0.0.1 --port 8000
```

## API Reference

### `POST /search`

```json
{
  "question": "蒸汽很小",
  "top_k": 5,
  "steps": 3,
  "decay": 0.7,
  "aggregate": "max",
  "kb_name": "default"
}
```

Response includes `build_id`, `search_time_ms`, and a `results` array — each result has `node_id / score / text / header / path / source_file / anchor_key`.

### `POST /rebuild`

Triggers an async rebuild from `docs_dir`. Returns `202 {task_id, status}` immediately; poll `GET /rebuild/{task_id}` for completion. Old graph keeps serving during rebuild (zero-downtime double-buffer swap).

### Anchor management

| Endpoint | Description |
|----------|-------------|
| `POST /anchor` | Set anchor: `{node_id, label, boost, propagation_boost}` |
| `DELETE /anchor/{anchor_key}` | Remove anchor |
| `GET /anchor` | List all anchors + unresolved |

Anchors survive rebuilds via stable `anchor_key` (sha256 of path+header+text prefix). Unresolved anchors are returned in the rebuild response.

### `GET /graph_info`

Returns node/edge counts, `build_id`, `meta`, and any `unresolved_anchors`.

## Configuration

`config.yaml` (all fields optional, shown with defaults):

```yaml
model:
  name: BAAI/bge-small-zh-v1.5   # use "hashing" for offline/test mode
  device: cpu
  batch_size: 32

graph:
  sim_threshold: 0.5
  parent_child_bonus: 0.2
  sibling_bonus: 0.1
  consecutive_bonus: 0.15

search:
  top_k: 5
  steps: 3
  decay: 0.7
  amplitude_cutoff: 0.01
  aggregate: max          # max | sum

anchor:
  default_boost: 2.0
  default_propagation_boost: 1.0   # >1.0 enables in-propagation amplification
  reconcile_threshold: 0.85

storage:
  data_dir: ./data
  schema_version: "1"
```

## Running Tests

```bash
uv run pytest tests/ -v
```

Uses `HashingEmbedder` (no HF download required) for all unit and E2E tests.

## Roadmap

| Milestone | Scope |
|-----------|-------|
| **M0** ✅ | Wave algorithm, anchors, JSON+NPZ storage, FastAPI, CLI, zero-downtime rebuild |
| **M1** | Dockerfile, JSON logs, `/health`+`/ready`, graceful shutdown, env-var config |
| **M2** | API key + rate limiting, multi-KB isolation, query cache |
| **M3** | Eval harness (precision@k / MRR), CI regression gate |
| **M4** | Prometheus metrics, OpenTelemetry traces |
| **post-v1** | Faiss/Qdrant vector backend, HA multi-replica, incremental updates |
