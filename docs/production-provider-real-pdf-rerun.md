# Production Provider Real PDF Rerun

Date: 2026-05-20

This rerun validates the production-provider profile after HTTP embedding batch-split hardening.

## Profile

- Config: `examples/config/production-provider-verification.yaml`
- Manuals: ASKO W6564 and HISENSE BSA5221 real PDFs
- Registry: SQLite
- Blob store: local Docker MinIO, S3-compatible
- Vector store: local Docker Qdrant
- Embedding: SiliconFlow `Qwen/Qwen3-Embedding-8B`

Secret values stayed in environment variables and are not included here.

## Outcome

Status: passed for real PDF rebuild, Qdrant sync, and search smoke.

The previous SiliconFlow embedding failure did not recur. The rerun embedded 423 chunks from the two PDFs. It then exposed a separate Qdrant write limit: one 423-point, 4096-dimensional upsert produced a JSON payload of about 37.4 MB, above Qdrant's 32 MB request limit. The vector store now splits Qdrant upserts into bounded batches, after which the same real PDF rebuild completed.

## Evidence

| Stage | Result | Evidence |
| --- | --- | --- |
| Bulk import | Passed | 2 imported, 0 failed |
| S3 blob verification | Passed | 2 checked, 0 missing |
| PDF rebuild and embedding | Passed | 423 embedded chunks |
| Qdrant sync | Passed | 423 points upserted |
| Qdrant inspect | Passed | 423 graph nodes, 423 Qdrant points, 0 missing vectors |
| Search smoke | Passed | 3 results returned for an ASKO W6564 drain-fault query |

Sanitized metrics:

```json
{
  "embedded_chunk_count": 423,
  "manuals_added": 2,
  "chunks_added": 411,
  "chunks_embedded": 411,
  "tag_embeddings_added": 2,
  "qdrant_points_upserted": 423,
  "qdrant_point_count": 423,
  "qdrant_missing_vector_count": 0,
  "search_result_count": 3
}
```

## Fix Made During Rerun

`QdrantVectorStore.update` now writes vectors in bounded upsert batches. This keeps high-dimensional real-PDF rebuilds below Qdrant's HTTP payload limit while preserving node id order, payload alignment, and existing validation behavior.

## Remaining Follow-Ups

1. DeepSeek answer/reranker live rerun was not part of this pass because the shell did not have `DEEPSEEK_API_KEY` set at task start. The prior fixture path already proved the DeepSeek integration with a larger answer budget.
2. The ASKO search smoke returned relevant source coverage but not the exact fault section for the English query. This is a retrieval-quality tuning topic, not a provider availability blocker.
3. The product-manual PDF parser emits "Rotated text discovered" warnings for these PDFs. Rebuild succeeds, but parser warning summarization could be cleaned up in a later operator UX task.
