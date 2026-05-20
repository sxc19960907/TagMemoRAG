# Production Provider E2E Pilot

Date: 2026-05-20

This report captures a local production-provider pilot using the merged provider profile:

- Config base: `examples/config/production-provider-verification.yaml`
- Vector store: local Docker Qdrant
- Blob store: local Docker MinIO, S3-compatible
- Embedding: SiliconFlow `Qwen/Qwen3-Embedding-8B`
- Reranker: SiliconFlow `Qwen/Qwen3-Reranker-0.6B`
- Answer generation: DeepSeek `deepseek-v4-flash`

Secret values were kept in environment variables only and are not included in this report.

## Outcome

Status: partial pass.

The end-to-end online stack passed for a small product-manual fixture and exposed two production follow-ups:

- Real PDF rebuilds reached parsing but failed during SiliconFlow embedding requests.
- DeepSeek answer generation needs a larger answer token budget and stronger citation enforcement.

## Passed Path

The successful pilot used the `washer_wm8.md` product-manual fixture through the same SQLite registry, S3 blob, Qdrant vector, SiliconFlow embedding/reranker, and DeepSeek answer path.

| Stage | Result | Evidence |
| --- | --- | --- |
| Bulk import | Passed | 1 manual imported, 0 failures |
| S3 blob verification | Passed | 1 object checked, 0 missing |
| Managed-library rebuild | Passed | 6 chunks embedded |
| Qdrant sync | Passed | 6 points upserted, 0 missing vectors |
| Retrieval | Passed | 6 results, 6 citations |
| SiliconFlow reranker | Passed | `qwen3-reranker-0.6b@siliconflow`, 6 items returned |
| DeepSeek answer | Passed with larger budget | `deepseek-v4-flash`, non-empty answer with 1024 token budget |

Key sanitized metrics:

```json
{
  "build_id": "20260520031731597102",
  "embedded_chunk_count": 6,
  "qdrant_points_upserted": 6,
  "qdrant_point_count": 6,
  "qdrant_missing_vector_count": 0,
  "s3_checked_count": 1,
  "s3_missing_count": 0,
  "retrieve_result_count": 6,
  "retrieve_citation_count": 6,
  "answer_text_len": 428,
  "answer_citation_count": 0,
  "rerank_latency_ms": 221
}
```

The top retrieved sections for the E21 drain query were:

- `E21 Drain Fault`
- `E-21 Pump Detail`
- `WM8 Washer Manual`

## Fixes Made During Pilot

The first `/answer` run exposed that the reranker dispatcher sent an empty query string to SiliconFlow. QueryPlan intentionally stores only `query_hash`, so the fix passes the runtime request question into the dispatcher without persisting raw query text.

The pilot also exposed that DeepSeek can return HTTP 200 with empty `message.content` when the output budget is too small. The OpenAI-compatible answer generator now treats empty content as `AnswerGenerationError` so the API returns `answer.kind=error` instead of a successful empty answer.

## Open Follow-Ups

1. Real PDF rebuild stability.
   - Tested PDFs: ASKO W6564 plus ASKO W6564 + HISENSE BSA5221.
   - Both attempts parsed the PDFs and then failed with `EmbeddingError: Embedding API request failed`.
   - Retry was attempted with `model.batch_size=4` and `timeout_seconds=60`.
   - Next step: capture sanitized HTTP error detail or add chunk-level retry/backoff for HTTP embedding rebuilds.

2. DeepSeek citation compliance.
   - Retrieval produced citations, but `deepseek-v4-flash` did not return structured citation ids.
   - Current citation validation correctly drops invalid or missing generation citations.
   - Next step: strengthen the answer prompt or post-process bracketed citation ids when supported by the model response.

3. Answer budget default for reasoning models.
   - `answer_token_budget=128` produced empty content for this model; the API now degrades this as `generation_failed`.
   - `answer_token_budget=1024` produced a non-empty answer.
   - Next step: document or configure a higher default for DeepSeek reasoning-style models.

4. Bulk import tag-order hint handling.
   - The fixture's multi-tag metadata triggered `TAG_ORDERING_HINT` during bulk import.
   - The underlying metadata validator treats this as non-blocking info, but bulk preview reports it as an error.
   - Next step: align bulk-import severity handling with metadata validation.
