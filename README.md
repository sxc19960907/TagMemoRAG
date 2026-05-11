# TagMemoRAG

TagMemoRAG is a Python semantic retrieval engine prototype for product-manual RAG. M0 implements Markdown/TXT parsing, graph construction, wave propagation search, anchors, JSON+NPZ persistence, FastAPI, and CLI entry points.

> **M0 scope note**: `kb_name` is reserved in the API/CLI but only `"default"` is supported. Multi-KB isolation lands in M2; passing any other value returns `404 KB_NOT_LOADED`.

## Install

```bash
pip install -e ".[dev]"
```

## Build A Knowledge Base

```bash
python -m tagmemorag build --docs tests/fixtures --kb default --config config.yaml
```

## Search

```bash
python -m tagmemorag search "蒸汽很小" --kb default --top-k 5
```

## Serve

```bash
python -m tagmemorag serve --host 127.0.0.1 --port 8000
```

Then query:

```bash
curl -X POST http://127.0.0.1:8000/search \
  -H "Content-Type: application/json" \
  -d '{"question":"蒸汽很小","top_k":5}'
```
