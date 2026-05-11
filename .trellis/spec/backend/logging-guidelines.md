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
- Anchor CRUD events by `anchor_key`, not by full anchor text.
- Storage schema mismatch or corrupted file load failures.

---

## What NOT to Log

- Full user queries by default.
- Full document chunks or raw manual text.
- API keys, future auth tokens, environment secrets, or local credentials.
- Embedding vectors.
- Stack traces in normal client-facing logs for known `ServiceError` cases.

---

## Future Milestones

M1 introduces JSON logs, `/health`, `/ready`, graceful shutdown, and model warm-up.

M4 introduces Prometheus metrics and OTel hook points. M0 should keep function boundaries clean enough that these can wrap search/build calls without rewriting the algorithm.
