# Production Provider Smoke Live Verification

Date: 2026-05-20

This run validates the merged production-provider smoke command against local Docker provider services and live external model providers.

## Profile

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
uv run python -m tagmemorag production-provider smoke \
  --config examples/config/production-provider-verification.yaml \
  --kb default \
  --manual 'product_manuals/washer/ASKO W6564.pdf' \
  --workdir .tmp/production-provider-verification/smoke \
  --output .tmp/production-provider-verification/provider-smoke-report.json \
  --format json \
  --question 'ASKO W6564 洗衣机不排水时应该检查什么？'
```

## Outcome

Status: passed.

The command completed with exit code 0. The full generated JSON report remains in `.tmp/` and is intentionally not committed because it is a runtime artifact. This document records only sanitized operational metrics.

## Evidence

| Stage | Result | Sanitized Evidence |
| --- | --- | --- |
| Config validation | Passed | 13 checks passed |
| Provider probe | Passed | embedding, answer, reranker, Qdrant, and S3 all passed |
| Manual import | Passed | 1 imported, 0 failed |
| Blob verification | Passed | 1 checked, 0 missing |
| Library rebuild | Passed | 185 embedded chunks |
| Qdrant sync | Passed | 185 points upserted in `full_sync` |
| Qdrant inspect | Passed | 185 graph nodes, 0 missing vectors |
| Reranker evidence | Passed | SiliconFlow reranker configured and no warnings |
| Answer smoke | Passed | DeepSeek answer produced 309 characters and 4 validated citations |

Sanitized metrics:

```json
{
  "provider_probe_passed": 5,
  "manuals_imported": 1,
  "blob_checked_count": 1,
  "blob_missing_count": 0,
  "embedded_chunk_count": 185,
  "qdrant_points_upserted": 185,
  "qdrant_graph_node_count": 185,
  "qdrant_missing_vector_count": 0,
  "answer_model_id": "deepseek-v4-flash",
  "answer_text_length": 309,
  "answer_citation_count": 4,
  "retrieve_result_count": 20,
  "retrieve_citation_count": 20
}
```

## Fix Made During Verification

The first live smoke run exposed a false-negative readiness probe for DeepSeek: the answer provider probe used only 64 output tokens, and `deepseek-v4-flash` spent that budget on `reasoning_content`, returning HTTP 200 with empty `content`. The real `/answer` path succeeded in the same run.

`provider_probe.answer` now uses a minimal cited readiness context and a 256-token budget. The follow-up probe passed with a non-empty answer and one citation, and the full production-provider smoke command then passed end-to-end.

## Notes

Qdrant inspection reported 185 graph nodes and 423 collection points because the local verification collection already contained points from earlier runs. Missing-vector count was 0, so the active graph was fully covered. A later operator cleanup task can add an explicit collection reset option for repeatable single-run point-count parity.
