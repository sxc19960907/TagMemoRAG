# Production provider verification profile

## Goal

Capture the production-like provider combination verified on 2026-05-20 as a reusable, secret-free local profile for future operators and agents.

## Requirements

- Add a config example for the verified stack:
  - Qdrant vector store on local Docker.
  - MinIO S3-compatible blob storage on local Docker.
  - SiliconFlow HTTP embeddings.
  - SiliconFlow reranker.
  - DeepSeek OpenAI-compatible answer generation.
- Add an environment template that names required variables without storing secret values.
- Document the exact local Docker startup and provider-probe sequence, including the Quay MinIO image fallback used when Docker Hub is unavailable.
- Preserve existing security posture: API keys stay in environment variables only and must not appear in committed YAML, docs, retained reports, or logs.
- Keep the profile operator-facing and consistent with existing production verification docs.

## Acceptance Criteria

- [x] `examples/config/` contains a secret-free production-provider verification config.
- [x] `.env.example` names the new provider env vars without raw credentials.
- [x] `docker-compose.yml` supports local Qdrant and MinIO verification services without changing the default app-only startup unexpectedly.
- [x] `docs/production-environment-verification.md` explains how to run the verified provider combination end to end.
- [x] Relevant docs/config tests or smoke checks pass.

## Notes

- Live verification already passed manually for embedding, reranker, answer, Qdrant, and S3. This task captures the reusable artifacts; it does not need to re-run external probes in CI.
