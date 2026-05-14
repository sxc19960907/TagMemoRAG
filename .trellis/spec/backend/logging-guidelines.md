# Logging Guidelines

> Logging conventions for TagMemoRAG.

---

## Overview

M0 keeps logging simple and uses Python's standard `logging` module. Full JSON logging and Prometheus/OTel integration belong to later milestones, but M0 code should already pass the fields that make those upgrades straightforward.

Logs should help answer:

- Which `build_id` served a search?
- Which `kb_name` was used?
- Did rebuild start, finish, fail, or get rejected?
- How long did build/search operations take?

---

## Log Levels

- `debug`: local diagnostics such as chunk counts per file or edge counts when useful in tests.
- `info`: lifecycle events such as KB loaded, rebuild started, rebuild completed, server started.
- `warning`: recoverable issues such as unresolved anchors after reconcile or a rejected concurrent rebuild.
- `error`: rebuild failure, storage load failure, model load failure, or unexpected API exceptions.

---

## Structured Fields

Even before JSON logging, use consistent `extra` fields or message keys where practical:

- `trace_id`
- `kb_name`
- `build_id`
- `task_id`
- `duration_ms`
- `chunk_count`
- `node_count`
- `edge_count`
- `unresolved_anchor_count`

Do not invent different names for the same concept in different modules.

---

## What to Log

- Application startup and KB load result.
- `POST /rebuild` accepted, rejected, completed, or failed.
- Search request summary: `trace_id`, `kb_name`, `build_id`, `top_k`, and duration.
- Search debug metadata may include low-cardinality lexical fields such as enabled/profile and candidate/source counts.
- Anchor CRUD events by `anchor_key`, not by full anchor text.
- Storage schema mismatch or corrupted file load failures.

---

## What NOT to Log

- Full user queries by default.
- Extracted lexical tokens or matched text snippets.
- Full document chunks or raw manual text.
- API keys, future auth tokens, environment secrets, or local credentials.
- Embedding vectors.
- Stack traces in normal client-facing logs for known `ServiceError` cases.

---

## Future Milestones

M1 introduces JSON logs, `/health`, `/ready`, graceful shutdown, and model warm-up.

M4 introduces Prometheus metrics and OTel hook points. M0 should keep function boundaries clean enough that these can wrap search/build calls without rewriting the algorithm.

## M4 Metrics and Tracing Contracts

### 1. Scope / Trigger

- Trigger: Prometheus `/metrics`, OpenTelemetry tracing, and business telemetry around search, cache, rate-limit, rebuild, KB load/build, and embedding.

### 2. Config Contract

- Config lives under `observability.metrics.*` and `observability.tracing.*`.
- Env keys use existing nesting, for example `TAGMEMORAG__OBSERVABILITY__METRICS__ENABLED=false`.
- Metrics default to enabled at `/metrics`; tracing defaults to disabled.
- `/metrics` belongs in default `auth.public_paths` so Prometheus can scrape authenticated deployments unless an operator explicitly changes the public path list.

### 3. Metrics Contract

- Custom metric names start with `tagmemorag_`.
- Allowed labels are only `method`, `route`, `status_code`, `kb_name`, `cache_status`, `error_code`, `operation`, and `outcome`.
- Never use raw query text, trace IDs, task IDs, API key identifiers or hashes, build IDs, source paths, document text, exception messages, or vectors as metric labels.
- Metrics recording helpers must not raise into the request or rebuild path.

### 4. Trace Contract

- Tracing setup must be idempotent and safe when no collector/exporter is configured.
- Business span names use the `tagmemorag.*` prefix, including `tagmemorag.search`, `tagmemorag.search.cache`, `tagmemorag.search.embedding`, `tagmemorag.search.wave`, `tagmemorag.rebuild`, `tagmemorag.kb.load`, `tagmemorag.kb.build`, and `tagmemorag.cache.clear`.
- Span attributes use low-sensitive `tagmemorag.*` fields such as `tagmemorag.kb_name`, `tagmemorag.build_id`, `tagmemorag.cache_status`, `tagmemorag.query_len`, `tagmemorag.result_count`, `tagmemorag.error_code`, and `tagmemorag.x_trace_id`.
- Do not put raw questions, document text, API keys, or embedding vectors in span attributes.

## M1 Observability Contracts

### 1. Scope / Trigger

- Trigger: JSON logging, request trace IDs, health/readiness probes, env-driven server config, and graceful shutdown.

### 2. Signatures

- `configure_logging(level: str = "INFO", format: "json" | "console" = "json") -> None`
- `GET /health -> text/plain`, always `200 ok` while the process can answer.
- `GET /ready -> text/plain`, `200 ok` only when model warm-up has completed and a KB is loaded.
- `python -m tagmemorag serve [--host HOST] [--port PORT] [--config PATH]`

### 3. Contracts

- Env keys use `TAGMEMORAG__` and double-underscore nesting, for example `TAGMEMORAG__SERVER__PORT=9000`.
- Config precedence is `env > .env > YAML > defaults`.
- Every HTTP response includes `X-Trace-Id`; if the request supplies `X-Trace-Id`, preserve it.
- `/search` response body includes the same `trace_id` as `X-Trace-Id`.
- `/search` log event includes `kb_name`, `build_id`, `query_len`, `top_k`, `result_count`, and `latency_ms`.

### 4. Validation & Error Matrix

- `AppState.is_shutting_down` and new `/rebuild` -> `503` with `SHUTTING_DOWN`.
- `/ready` when `embedder_ready` is false -> `503 embedder not ready`.
- `/ready` when KB is missing -> `503 kb not loaded`.
- Known `ServiceError` responses keep `{code, message, detail}`; probe endpoints deliberately use short text.

### 5. Good/Base/Bad Cases

- Good: `TAGMEMORAG__SERVER__PORT=9000 python -m tagmemorag serve` listens on 9000.
- Base: no KB on first boot means `/health=200` and `/ready=503`.
- Bad: Docker CMD hardcodes `--host` or `--port`, making env overrides ineffective.

### 6. Tests Required

- Env precedence test with YAML and `TAGMEMORAG__SERVER__PORT`.
- Trace test for generated and preserved `X-Trace-Id`.
- Probe tests for not-ready, loaded-ready, and shutdown states.
- CLI serve test proving `--config` host/port reaches `uvicorn.run`.

### 7. Wrong vs Correct

#### Wrong

```python
uvicorn.run("tagmemorag.api:app", host=args.host, port=args.port)
```

This imports the API module with import-time defaults and ignores a custom config path for application state.

#### Correct

```python
from . import api

api.settings = cfg
uvicorn.run(api.app, host=args.host or cfg.server.host, port=args.port or cfg.server.port)
```
