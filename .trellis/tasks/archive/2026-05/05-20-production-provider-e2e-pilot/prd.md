# Production provider end-to-end pilot

## Goal

Verify the merged production-provider profile against real product manuals end to end: manual ingestion, S3 blob storage, Qdrant vector storage, retrieval, reranking, and DeepSeek answer generation.

## Requirements

- Use `examples/config/production-provider-verification.yaml` as the target profile.
- Use local Docker Qdrant and MinIO for storage validation.
- Use SiliconFlow for embedding and reranker calls.
- Use DeepSeek only through the configured `DEEPSEEK_API_KEY` environment variable; do not persist secret values.
- Run a real-manual pilot on the repository's product manuals and retain a sanitized evidence report.
- Capture actionable results: pass/fail, provider probe status, Qdrant collection/point state, MinIO blob state, retrieval/rerank/answer smoke, and any follow-up gaps.

## Acceptance Criteria

- [x] Real manuals are ingested or rebuilt using the production-provider profile.
- [x] Qdrant contains expected vectors for the pilot KB.
- [x] MinIO contains expected manual blobs for the pilot KB.
- [x] Retrieval returns citations for at least one real product-manual query.
- [x] Reranker and answer generation are exercised with live providers.
- [x] A secret-free pilot evidence document is committed under `docs/`.

## Notes

- This is an operator verification task. Avoid code changes unless the pilot exposes a real product bug.
