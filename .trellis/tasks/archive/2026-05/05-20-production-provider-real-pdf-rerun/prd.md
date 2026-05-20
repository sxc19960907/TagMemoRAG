# Production provider real PDF rerun

## Goal

Rerun the production-provider profile against real ASKO/HISENSE PDF manuals after HTTP embedding batch-split hardening, and record whether the previous SiliconFlow embedding failure is resolved.

## Requirements

- Use `examples/config/production-provider-verification.yaml`.
- Use local Docker Qdrant and MinIO.
- Use SiliconFlow for embeddings/reranker; keep secret values in environment only.
- Use DeepSeek only if an environment key is available; absence of the key must not block the embedding rebuild validation.
- Capture sanitized evidence: import counts, blob verification, rebuild status, Qdrant point counts, and safe embedding error detail if the rebuild still fails.

## Acceptance Criteria

- [x] ASKO/HISENSE PDFs are imported into the configured SQLite registry/S3 blob store or the import failure is recorded.
- [x] Managed-library rebuild is attempted with the live HTTP embedding provider.
- [x] If rebuild succeeds, Qdrant contains expected vectors and the report records point counts.
- [x] If rebuild fails, the report records the sanitized `EMBEDDING_FAILED` detail exposed by the hardened embedder.
- [x] No API keys, Authorization headers, raw provider bodies, raw PDF text, or vectors are written to committed files.
