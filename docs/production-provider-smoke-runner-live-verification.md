# Production Provider Smoke Runner Live Verification

Date: 2026-05-20

This run validates the one-command production-provider smoke runner against local Docker Qdrant/MinIO and live SiliconFlow/DeepSeek providers.

## Profile

- Runner: `scripts/run_production_provider_smoke.py`
- Config: `examples/config/production-provider-verification.yaml`
- Manual: `product_manuals/washer/ASKO W6564.pdf`
- Registry: SQLite
- Blob store: local Docker MinIO, S3-compatible
- Vector store: local Docker Qdrant
- Embedding: SiliconFlow `Qwen/Qwen3-Embedding-8B`
- Reranker: SiliconFlow `Qwen/Qwen3-Reranker-0.6B`
- Answer: DeepSeek `deepseek-v4-flash`

Secret values stayed in environment variables and are not included here.

## Command

```bash
TAGMEMORAG_S3_ACCESS_KEY=... \
TAGMEMORAG_S3_SECRET_KEY=... \
DEEPSEEK_API_KEY=... \
uv run python scripts/run_production_provider_smoke.py
```

The runner starts the local provider services, ensures the configured MinIO bucket, resets the Qdrant verification collection, and runs the production-provider smoke command with the default ASKO W6564 manual.

## Outcome

Status: passed.

The runner completed with exit code 0. The full generated JSON reports remain in `.tmp/` and are intentionally not committed because they are runtime artifacts. This document records only sanitized operational metrics.

## Runner Evidence

| Runner Check | Result | Sanitized Evidence |
| --- | --- | --- |
| Required env | Passed | All required variable names were present |
| Docker providers | Passed | `docker compose --profile providers up -d qdrant minio` exited 0 |
| S3 bucket | Passed | Bucket `tagmemorag-verify` already existed |
| Production-provider smoke | Passed | Nested smoke command exited 0 |

Sanitized runner summary:

```json
{
  "status": "passed",
  "smoke_exit_code": 0,
  "required_env": "passed",
  "docker_providers": "passed",
  "s3_bucket": "passed",
  "production_provider_smoke": "passed"
}
```

## Nested Smoke Evidence

| Smoke Stage | Result | Sanitized Evidence |
| --- | --- | --- |
| Config validation | Passed | 13 checks passed |
| Provider probe | Passed | embedding, answer, reranker, Qdrant, and S3 all passed |
| Qdrant reset | Passed | Verification collection deleted before rebuild |
| Manual import | Passed | 1 imported, 0 failed |
| Blob verification | Passed | 1 checked, 0 missing |
| Library rebuild | Passed | 185 chunks embedded, 185 Qdrant points upserted |
| Qdrant inspect | Passed | 185 graph nodes, 185 Qdrant points, 0 missing vectors |
| Reranker evidence | Passed | SiliconFlow reranker configured and no warnings |
| Answer smoke | Passed | DeepSeek answer kind `answer`, 3 citations, no warnings |

Sanitized nested metrics:

```json
{
  "provider_probe_passed": 5,
  "qdrant_reset_action": "deleted",
  "manuals_imported": 1,
  "blob_checked_count": 1,
  "blob_missing_count": 0,
  "embedded_chunk_count": 185,
  "qdrant_points_upserted": 185,
  "qdrant_graph_node_count": 185,
  "qdrant_point_count": 185,
  "qdrant_missing_vector_count": 0,
  "answer_kind": "answer",
  "answer_model_id": "deepseek-v4-flash",
  "answer_text_length": 259,
  "answer_citation_count": 3,
  "retrieve_result_count": 20,
  "retrieve_citation_count": 20
}
```

## Notes

- The one-command runner is now the recommended local operator path for production-provider verification.
- Qdrant point count matched graph node count after the reset, so the verification collection contains exactly the active graph vectors for this run.
- Answer bodies, retrieval excerpts, provider credentials, and `.tmp/` reports were not committed.
