# DeepSeek Real PDF Answer Rerun

Date: 2026-05-20

This rerun validates `/answer` on the real ASKO W6564 and HISENSE BSA5221 PDF knowledge base after the production-provider rebuild path passed with SiliconFlow embeddings and Qdrant vectors.

## Profile

- Config: `examples/config/production-provider-verification.yaml`
- Manuals: ASKO W6564 and HISENSE BSA5221 real PDFs
- Vector store: local Docker Qdrant
- Blob store: local Docker MinIO
- Embedding: SiliconFlow `Qwen/Qwen3-Embedding-8B`
- Reranker: SiliconFlow `Qwen/Qwen3-Reranker-0.6B`
- Answer generation: DeepSeek `deepseek-v4-flash`

Secret values stayed in process environment variables and are not included here.

## Outcome

Status: passed with known citation gap.

The real PDF `/answer` path reached all intended online providers:

1. Real PDF KB rebuild completed with 423 embedded chunks.
2. Qdrant sync completed with 423 points upserted.
3. `/answer` retrieved answerable evidence from the real PDF KB.
4. SiliconFlow reranker ran as Tier-1 online reranker.
5. DeepSeek generated a non-empty answer when the answer token budget was large enough.

## Evidence

| Stage | Result | Evidence |
| --- | --- | --- |
| KB rebuild | Passed | 423 embedded chunks |
| Qdrant sync | Passed | 423 points upserted |
| Retrieve evidence | Passed | 20 retrieve results and 20 retrieve citations |
| SiliconFlow reranker | Passed | `qwen3-reranker-0.6b@siliconflow`, top_n 20, no warnings |
| DeepSeek answer, 128 token budget | Failed safely | `answer.kind=error`, `generation_failed` |
| DeepSeek answer, 1024 token budget | Passed | non-empty answer, 434-453 characters |
| Answer citations | Gap | 0 validated answer citations |

Sanitized metrics:

```json
{
  "embedded_chunk_count": 423,
  "qdrant_points_upserted": 423,
  "retrieve_result_count": 20,
  "retrieve_citation_count": 20,
  "reranker_vendor": "qwen3-reranker-0.6b@siliconflow",
  "reranker_top_n_returned": 20,
  "reranker_latency_ms": 1271,
  "answer_model_id": "deepseek-v4-flash",
  "answer_budget_128_kind": "error",
  "answer_budget_1024_kind": "answer",
  "answer_budget_1024_text_len": 434,
  "answer_citation_count": 0
}
```

## Interpretation

DeepSeek is now verified as reachable and usable in the real-PDF answer path. The remaining issue is not provider connectivity; it is answer contract compliance. Retrieval produced citations, but the model did not return citations in the structured format accepted by `validate_generation_citations`, so the answer payload carried zero validated answer citations.

The 128-token run also reconfirmed the earlier pilot finding: this DeepSeek model needs a larger answer token budget. The current empty/failed generation behavior is safe because it degrades to `answer.kind=error` instead of returning a successful blank answer.

## Remaining Follow-Ups

1. Raise or document the default answer token budget for DeepSeek-style reasoning models.
2. Strengthen the answer prompt so generated answers include valid citation ids from the provided context.
3. Consider a post-processing pass for bracketed citation ids if the model returns recognizable but not schema-valid citations.
