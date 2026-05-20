# Quality Guidelines

> Code quality standards for TagMemoRAG backend development.

---

## Overview

TagMemoRAG should be implemented as a small, testable Python package. Prefer explicit dataclasses, typed function signatures, deterministic tests, and narrow module boundaries.

M0 quality is defined by the acceptance criteria in `.trellis/tasks/05-10-wave-rag-implementation/prd.md` and the phase checklist in `implement.md`.

---

## Required Patterns

- Keep pure algorithm modules side-effect-free where practical.
- Use dataclasses for core contracts: `Chunk`, `Anchor`, `Result`, and `GraphState`.
- Normalize embeddings once and treat dot product as cosine similarity.
- Keep graph node ids as integers and store stable identity separately as `anchor_key`.
- Store vectors outside the NetworkX graph.
- Use atomic file replacement for persistent files.
- Keep rebuild double-buffer behavior: build new state off to the side, then swap only after success.
- Include `build_id` in search results and relevant logs.
- Use explicit config objects instead of scattering constants across modules.
- Keep hybrid lexical retrieval local and bounded: scan loaded graph node fields only, respect filters and KB boundaries, and keep final ranking deterministic over the loaded graph and vectors.
- Match normalized English metadata aliases on token boundaries, not substrings, so `washer` never narrows a `dishwasher` query.
- For `BaseSettings` configs that merge YAML with env vars, explicitly test precedence. The M1 contract is `env > .env > YAML init data > defaults`; pydantic-settings does not preserve that order unless `settings_customise_sources` is configured.

---

## Forbidden Patterns

- Do not use pickle for persisted graph state.
- Do not let `/search` mutate graph, anchors, config, or storage.
- Do not make algorithm modules import FastAPI, CLI, or global app state.
- Do not make rebuild failures replace or clear the currently served graph.
- Do not silently drop unresolved anchors after rebuild.
- Do not introduce new production dependencies without updating `pyproject.toml`, tests, and this spec if behavior changes.
- Do not emit raw lexical query tokens, matched document snippets, full candidate ids, vectors, or source-file lists in debug metadata, logs, metrics, traces, or cache suffixes.
- Do not hand-roll string parsing for JSON/YAML/NPZ files when standard libraries or project storage helpers are available.

---

## Testing Requirements

M0 requires focused tests for:

- Parser edge cases: empty file, no headings, nested headings, long-block split, short-block merge.
- Embedder shape and normalization. Use a fake embedder in unit tests when model download would be too expensive.
- Graph builder semantic, parent-child, sibling, and consecutive edges.
- Wave search max vs sum aggregation, anchor boost, propagation boost, and deterministic ranking.
- Storage round-trips for graph, vectors, anchors, and meta.
- AppState rebuild concurrency: searches keep using old graph while rebuild runs.
- API error format and anchor/rebuild/search paths.
- E2E coffee-machine fixture queries, including `"蒸汽很小"`.

Tests should avoid network access by default. Heavy model tests should be opt-in or use fixtures/mocks unless the task explicitly requires real model verification.

---

## Code Review Checklist

- Does the change preserve the layer boundaries from `design.md`?
- Are config defaults centralized?
- Are API, CLI, and tests using the same data contracts?
- Are errors returned as `{code, message, detail}`?
- Are storage writes atomic?
- Does rebuild failure leave the old state intact?
- Are new files covered by unit or E2E tests proportional to risk?
- Did the implementation avoid scope creep from M1-M4?

---

## Common Mistakes

- Optimizing for future HA before M0 is correct.
- Baking default paths or thresholds into several modules.
- Passing a custom `--config` only to the CLI wrapper while serving a separately imported FastAPI app with import-time defaults. If `serve --config path.yaml` is supported, inject the loaded `Settings` into the API module before calling `uvicorn.run`.
- Putting blank optional numeric env vars into `.env.example` when the file is also used by `docker compose env_file`; empty strings do not parse as `int | None`.
- Testing only happy-path search while missing rebuild and storage failure paths.
- Treating `node_id` as stable across rebuilds.
- Forgetting that `implement.jsonl` and `check.jsonl` determine what future agents automatically load.

## Scenario: HTTP Embedding Provider

### 1. Scope / Trigger

- Trigger: embedding provider can be local, hashing, or OpenAI-compatible HTTP.

### 2. Signatures

- `create_embedder(model_name, device, batch_size, dim, provider, base_url, embeddings_url, api_key_env, timeout_seconds, dimensions, normalize)`
- `HttpEmbedder.encode_batch(texts: Sequence[str]) -> np.ndarray`
- `HttpEmbedder.encode_query(text: str) -> np.ndarray`

### 3. Contracts

- Config keys live under `model.*`: `provider`, `name`, `dim`, `batch_size`, `base_url`, `embeddings_url`, `api_key_env`, `timeout_seconds`, `dimensions`, `normalize`.
- `provider=http` sends `POST {base_url.rstrip("/")}/embeddings` unless `embeddings_url` is set.
- Request body includes `model`, `input`, `encoding_format="float"`, and optional `dimensions`.
- API key is read only from `os.environ[api_key_env]`; never store secret values in YAML or logs.
- Response must contain `data[].embedding`; sort by `data[].index` when present.
- Returned vectors are `np.float32` and normalized by default to preserve dot-product-as-cosine semantics.

### 4. Validation & Error Matrix

- Missing API key env -> `INVALID_CONFIG`.
- HTTP status error -> `EMBEDDING_FAILED` with status code and endpoint.
- Network/timeout/invalid JSON -> `EMBEDDING_FAILED`.
- Missing or malformed response vectors -> `EMBEDDING_FAILED`.

### 5. Good/Base/Bad Cases

- Good: SiliconFlow-compatible config uses `base_url=https://api.siliconflow.cn/v1` and `api_key_env=SILICONFLOW_API_KEY`.
- Base: local provider remains default for offline deployment.
- Bad: passing raw API keys in `config.yaml` or logging request headers.

### 6. Tests Required

- Payload shape includes `model`, `input`, `encoding_format`, optional `dimensions`, and Bearer header.
- Full `embeddings_url` overrides `base_url`.
- Missing API key and HTTP errors map to project errors.
- Env override test for `TAGMEMORAG__MODEL__PROVIDER=http`.

### 7. Wrong vs Correct

#### Wrong

```yaml
model:
  provider: http
  api_key: sk-...
```

#### Correct

```yaml
model:
  provider: http
  api_key_env: SILICONFLOW_API_KEY
```

## Scenario: HTTP Embedding Large Batch Failure Hardening

### 1. Scope / Trigger

- Trigger: HTTP embedding providers may reject or time out on larger PDF-derived batches even when single-query readiness probes pass.

### 2. Signatures

- `HttpEmbedder.encode_batch(texts: Sequence[str]) -> np.ndarray`
- `HttpEmbedder._request_batch_with_split(texts: Sequence[str]) -> np.ndarray`
- `HttpEmbedder._failure_detail(texts, split_attempted, status_code=None, error_type=None) -> dict[str, object]`

### 3. Contracts

- `model.batch_size` is the maximum HTTP embedding request size, not a guarantee that every provider accepts that request.
- A failed multi-item HTTP embedding request must be retried by splitting into smaller sub-batches before surfacing a final failure.
- Successful split retries must preserve input order and existing normalization behavior.
- Failure detail may include endpoint, status/error type, batch size, min/max text length, total text length, and split-attempt status.
- Failure detail must not include raw document text, request body, Authorization headers, API keys, provider response body, vectors, source paths, or snippets.

### 4. Validation & Error Matrix

- HTTP status failure on multi-item batch -> split retry; if sub-batches pass, return vectors.
- HTTP status failure on single-item batch -> `EMBEDDING_FAILED` with sanitized detail.
- Network/timeout/invalid JSON on multi-item batch -> split retry; if sub-batches fail, surface sanitized final detail.
- Vector count/shape/content validation failures -> `EMBEDDING_FAILED` as before.

### 5. Good/Base/Bad Cases

- Good: 32-item request fails, two 16-item requests pass, rebuild continues with vectors in original order.
- Base: configured batch succeeds on first request; no fallback is visible to callers.
- Bad: error detail includes provider body or raw PDF text to help debugging.

### 6. Tests Required

- Multi-item batch failure falls back to smaller HTTP calls and preserves vector order.
- Final failure detail contains safe numeric diagnostics and no raw text or secret values.
- Existing payload, endpoint override, dotenv key, missing key, and provider factory tests remain green.

### 7. Wrong vs Correct

#### Wrong

```python
detail = {"endpoint": endpoint, "body": provider_error_body, "input": texts}
```

#### Correct

```python
detail = {
    "endpoint": endpoint,
    "batch_size": len(texts),
    "max_text_chars": max(len(text) for text in texts),
    "split_attempted": True,
}
```

## Scenario: Qdrant Large Vector Upsert Hardening

### 1. Scope / Trigger

- Trigger: Qdrant-backed rebuilds can exceed the server HTTP JSON payload limit when one upsert contains hundreds of high-dimensional vectors.

### 2. Signatures

- `QdrantVectorStore.update(ids: np.ndarray, vecs: np.ndarray, payloads: list[dict[str, Any]] | None = None) -> None`
- `QdrantVectorStore.add(ids: np.ndarray, vecs: np.ndarray, payloads: list[dict[str, Any]] | None = None) -> None`

### 3. Contracts

- Qdrant vector writes must be split into bounded upsert calls while preserving node id order and payload alignment.
- Dimension checks, id/vector count checks, and payload count checks run before any upsert batch is sent.
- Payloads must continue through `_safe_payload`; raw chunk text and vectors must not be stored as Qdrant payload fields.
- Batch sizing is an implementation limit, not user-facing config, unless a future task proves operators need a setting.

### 4. Validation & Error Matrix

- Oversized vector set -> multiple upsert calls; rebuild can continue if all batches succeed.
- Any batch failure -> `STORAGE_LOAD_FAILED` with collection and safe provider error detail; active graph remains unchanged.
- Payload count mismatch -> `STORAGE_SCHEMA_MISMATCH` before writing.
- Vector dimension mismatch -> `STORAGE_SCHEMA_MISMATCH` before writing.

### 5. Good/Base/Bad Cases

- Good: 423 vectors with 4096 dimensions are written as several smaller Qdrant upserts.
- Base: small vector sets still write successfully; callers do not need to know batching occurred.
- Bad: increasing Qdrant server request limits is the only fix, or storing fewer payload safety fields to squeeze under the limit.

### 6. Tests Required

- Unit test proves a large `QdrantVectorStore.update` call is split into ordered upsert batches.
- Existing Qdrant save/load, inspect, and incremental sync tests remain green.
- Real-provider pilot should inspect Qdrant point count and missing-vector count after rebuild.

### 7. Wrong vs Correct

#### Wrong

```python
client.upsert(collection_name=collection, points=all_points)
```

#### Correct

```python
for batch in batches:
    client.upsert(collection_name=collection, points=batch)
```

## Scenario: Production Pilot Command

### 1. Scope / Trigger

- Trigger: adding or changing `tagmemorag pilot run`, the operator-facing pre-pilot gate that composes config validation, provider probe, readiness smoke, and eval.
- This is a cross-layer CLI/service/report contract. Keep the CLI thin and put report assembly in `src/tagmemorag/production_pilot.py`.

### 2. Signatures

- CLI: `python -m tagmemorag pilot run --config <path> --suite <jsonl> --docs <dir> --workdir <dir> --output <path> --format json|markdown`
- Service: `run_production_pilot(config_path, suite_path, docs_path, workdir, top_k, source_k, thresholds) -> ProductionPilotReport`
- Writer: `write_pilot_report(report, path, fmt="json"|"markdown") -> None`

### 3. Contracts

- Response schema version: `production_pilot.v1`.
- Report fields: `status`, `config_path`, `suite_path`, `docs_path`, `workdir`, `stages`, `next_steps`.
- Stage fields: `name`, `status`, `detail`, optional `error`.
- Allowed detail content: stage counts, provider/check names, profile names, numeric eval metrics, eval suite filename, failed case ids.
- Forbidden detail content: raw eval queries, retrieved snippets, vectors, full source-file lists, API keys, Authorization headers, raw provider responses, generated answer text.
- Default local pilot thresholds may be lower than strict `eval run` defaults when documented as pilot-specific; strict regression gating should use `eval run --baseline`.

### 4. Validation & Error Matrix

- `config_validate.status == failed` -> pilot status `failed`.
- `provider_probe.status == failed` -> pilot status `failed`.
- `provider_probe.status == skipped` -> allowed for local/offline profiles.
- `readiness_smoke.status != passed` -> pilot status `failed`.
- `eval.summary.passed is false` -> pilot status `failed`.
- Runtime exceptions that prevent report creation -> CLI prints `pilot error: <type>: <reason>` to stderr and exits `2`.

### 5. Good/Base/Bad Cases

- Good: local hashing/NPZ pilot exits `0`, provider stage is all skipped, readiness and eval pass, and JSON/Markdown report is retained.
- Base: warning config checks produce pilot `warning` unless a later required stage fails.
- Bad: dumping `EvalReport.to_dict()` into the pilot report leaks queries and snippets; summarize only `summary.metrics`, counts, and failed case ids.

### 6. Tests Required

- Real local pilot test with hashing config and fixture data.
- Sanitization assertions that fixture queries/snippets and `actual_top_k` do not appear in the pilot report JSON.
- CLI tests for JSON file output, Markdown stdout, and failed report exit code.
- Failure aggregation test using intentionally strict thresholds.

### 7. Wrong vs Correct

#### Wrong

```python
stage_detail = eval_report.to_dict()
```

#### Correct

```python
stage_detail = {
    "cases": eval_report.summary.cases,
    "metrics": eval_report.summary.metrics.to_dict(),
    "failed_cases": [case.id for case in eval_report.cases if not case.passed],
}
```
