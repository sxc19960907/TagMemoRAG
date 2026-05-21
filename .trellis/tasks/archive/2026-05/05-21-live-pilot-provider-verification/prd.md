# Live Pilot Provider Verification

## Goal

Run and retain a live production-provider pilot verification using local Docker Qdrant/MinIO, SiliconFlow embedding/reranker, and DeepSeek answer provider.

## User Value

The project already has smoke-level live provider evidence. This task proves the next delivery gate: the unified provider verification command can run the retained pilot report path and produce sanitized evidence that operators can use before opening small pilot traffic.

## Confirmed Facts

- The project is on `master` with a clean working tree and no active Trellis task when this task starts.
- The unified command is `uv run python -m tagmemorag production-provider verify --level pilot`.
- The production-provider config is `examples/config/production-provider-verification.yaml`.
- That config uses:
  - SiliconFlow HTTP embedding model `Qwen/Qwen3-Embedding-8B`.
  - SiliconFlow reranker model `Qwen/Qwen3-Reranker-0.6B`.
  - DeepSeek OpenAI-compatible answer model `deepseek-v4-flash` at `https://api.deepseek.com`.
  - Local Qdrant at `http://localhost:6333`.
  - Local MinIO at `http://localhost:9000`.
- The checked-in Docker provider profile starts Qdrant and MinIO via `docker compose --profile providers up -d qdrant minio`.
- Existing runbooks recommend retaining a pilot report and, when using diagnosis, passing hashing and SiliconFlow aggregate baselines with informational/accepted suite policy.

## Requirements

- Run the live provider pilot through the unified `production-provider verify --level pilot` path.
- Use local Docker Qdrant and MinIO unless already-running services force the verified `warning` path.
- Keep provider keys out of files, command logs, docs, and committed artifacts.
- Retain local runtime evidence under `.tmp/production-provider-verification/`.
- Produce a sanitized committed summary document, not raw provider responses or secrets.
- If the pilot fails, identify the failing stage and capture the next corrective task instead of silently loosening thresholds.
- Do not broaden scope into LangChain/RAG optimization review; that remains deferred.

## Acceptance Criteria

- [x] Required env names are present without printing secret values.
- [x] Docker provider readiness is verified, or an already-running-services `warning` is explicitly explained.
- [x] Unified `production-provider verify --level pilot` completes and writes a top-level verify summary.
- [x] Nested smoke report is retained locally and summarized with sanitized stage counts.
- [x] Pilot report is retained locally and summarized with sanitized stage status, eval metrics, and next steps.
- [x] Committed docs contain no API keys, Authorization headers, raw answer text, retrieved snippets, or raw provider responses.
- [x] Trellis task is archived and journaled after verification.

## Out Of Scope

- Reauthoring eval suites or changing acceptance thresholds.
- Replacing project-native RAG logic with LangChain.
- Service deployment, public traffic, or browser/API service checks beyond the CLI verification path.
