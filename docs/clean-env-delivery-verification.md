# Clean Environment Delivery Verification

Date: 2026-05-20

This run verifies the MVP delivery guide from isolated runtime paths under `.tmp/clean-env-delivery/`. It does not depend on prior `.tmp/production-provider-verification/` reports.

## Scope

- Guide verified: `docs/mvp-delivery-guide.md`
- Local deterministic workdir: `.tmp/clean-env-delivery/readiness`
- Live provider verify workdir: `.tmp/clean-env-delivery/operator-smoke`
- Live provider verify summary: `.tmp/clean-env-delivery/verify-summary.json`
- Nested smoke report: `.tmp/clean-env-delivery/operator-smoke-report.json`

Secret values stayed in environment variables and are not included here.

## Commands

Local composition:

```bash
uv run python -m tagmemorag readiness smoke \
  --workdir .tmp/clean-env-delivery/readiness \
  --keep-workdir
```

Command help checks:

```bash
uv run python -m tagmemorag production-provider verify --help
uv run python -m tagmemorag readiness smoke --help
uv run python -m tagmemorag pilot run --help
```

Live provider smoke with already-running local provider services:

```bash
TAGMEMORAG_S3_ACCESS_KEY=... \
TAGMEMORAG_S3_SECRET_KEY=... \
DEEPSEEK_API_KEY=... \
uv run python -m tagmemorag production-provider verify \
  --level smoke \
  --skip-docker \
  --workdir .tmp/clean-env-delivery/operator-smoke \
  --output .tmp/clean-env-delivery/operator-smoke-report.json \
  --verify-output .tmp/clean-env-delivery/verify-summary.json
```

## Outcome

Status: passed.

Raw runtime reports remain under `.tmp/clean-env-delivery/` and are intentionally not committed. This document records only sanitized metrics.

## Local Readiness Evidence

| Check | Result | Sanitized Evidence |
| --- | --- | --- |
| Build | Passed | 1 chunk |
| Retrieve answer | Passed | 1 evidence item |
| QueryPlan | Passed | 1 persisted row |
| Bundle round-trip | Passed | 1 exported manual, 1 imported manual |

## Command Help Evidence

| Command | Result | Sanitized Evidence |
| --- | --- | --- |
| `production-provider verify --help` | Passed | Help rendered with 61 lines |
| `readiness smoke --help` | Passed | Help rendered with 6 lines |
| `pilot run --help` | Passed | Help rendered with 32 lines |

## Live Verify Evidence

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
  "answer_text_length": 329,
  "answer_citation_count": 5,
  "retrieve_result_count": 20,
  "retrieve_citation_count": 20
}
```

## Follow-Up

- The clean run reused already-running Docker provider services with `--skip-docker`. The known Docker startup diagnostics task remains the next planned fix.
- A dedicated live pilot verification still needs an explicit eval suite/baseline and provider-cost budget before running `production-provider verify --level pilot`.
