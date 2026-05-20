# Unified Verify CLI Live Verification

Date: 2026-05-20

This run validates the merged `production-provider verify` CLI against local Docker Qdrant/MinIO services and live SiliconFlow/DeepSeek providers.

## Profile

- Command: `python -m tagmemorag production-provider verify`
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

The first live attempt used the default Docker-starting path:

```bash
TAGMEMORAG_S3_ACCESS_KEY=... \
TAGMEMORAG_S3_SECRET_KEY=... \
DEEPSEEK_API_KEY=... \
uv run python -m tagmemorag production-provider verify \
  --level smoke \
  --verify-output .tmp/production-provider-verification/unified-verify-smoke-summary.json
```

That attempt produced a failed top-level verify summary because the `docker_providers` step returned exit code 1. The same run still confirmed S3 and the nested production-provider smoke path, and the nested smoke report passed end-to-end.

The accepted live verification used already-running local provider services:

```bash
TAGMEMORAG_S3_ACCESS_KEY=... \
TAGMEMORAG_S3_SECRET_KEY=... \
DEEPSEEK_API_KEY=... \
uv run python -m tagmemorag production-provider verify \
  --level smoke \
  --skip-docker \
  --verify-output .tmp/production-provider-verification/unified-verify-smoke-summary-skip-docker.json
```

The generated JSON reports remain in `.tmp/` and are intentionally not committed because they are runtime artifacts. This document records only sanitized operational metrics.

## Outcome

Status: passed with `--skip-docker`.

The full default path exposed one operator follow-up: the verify summary currently records only Docker exit code, not bounded stderr/reason detail. Manual `docker compose --profile providers up -d qdrant minio` succeeded immediately afterward, and the provider services were reachable for S3, Qdrant, provider probes, rebuild, and answer smoke.

## Verify Evidence

| Verify Check | Result | Sanitized Evidence |
| --- | --- | --- |
| Required env | Passed | All required variable names were present |
| Docker providers | Skipped | Existing local provider services were reused |
| S3 bucket | Passed | Bucket `tagmemorag-verify` already existed |
| Production-provider smoke | Passed | Nested smoke command exited 0 |

Sanitized verify summary:

```json
{
  "status": "passed",
  "level": "smoke",
  "smoke_exit_code": 0,
  "required_env": "passed",
  "docker_providers": "skipped",
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
| Answer smoke | Passed | DeepSeek answer kind `answer`, 5 citations, no warnings |

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
  "answer_text_length": 368,
  "answer_citation_count": 5,
  "retrieve_result_count": 20,
  "retrieve_citation_count": 20
}
```

## Pilot Decision

`--level pilot` was deferred from this live verification task. The smoke level already performed the high-cost live rebuild, provider probe, reranker evidence check, and DeepSeek answer check. A separate pilot live task should run `--level pilot` with an explicit suite/baseline choice and cost/runtime budget, rather than hiding that additional provider spend inside this smoke acceptance pass.

## Follow-Up

- Improve `production-provider verify` Docker diagnostics so a failed Docker start step records bounded, sanitized stderr/reason detail.
- Consider treating `docker_providers` as a warning when Docker start fails but subsequent S3/Qdrant provider probes and nested smoke pass.
- Run a dedicated live pilot verification with explicit eval suite and baseline settings.
