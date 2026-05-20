# DeepSeek Citation Live Verification

Date: 2026-05-20

This verifies the merged DeepSeek answer-budget and text-citation extraction changes against the real ASKO W6564 and HISENSE BSA5221 PDF knowledge base.

## Profile

- Config: `examples/config/production-provider-verification.yaml`
- Manuals: ASKO W6564 and HISENSE BSA5221 real PDFs
- Embedding: SiliconFlow `Qwen/Qwen3-Embedding-8B`
- Reranker: SiliconFlow `Qwen/Qwen3-Reranker-0.6B`
- Vector store: local Docker Qdrant
- Blob store: local Docker MinIO
- Answer generation: DeepSeek `deepseek-v4-flash`

Secret values stayed in process environment variables and are not included here.

## Outcome

Status: passed.

The merged changes resolved both previously observed DeepSeek answer-path gaps for this live verification profile:

- The profile default answer budget is now 1024 tokens, and `/answer` succeeded without a per-request override.
- DeepSeek returned citation ids in answer text; the OpenAI-compatible parser extracted and validated them against the retrieve allowlist.

## Evidence

| Stage | Result | Evidence |
| --- | --- | --- |
| Real PDF rebuild | Passed | 423 embedded chunks |
| Qdrant sync | Passed | 423 points upserted |
| Retrieve evidence | Passed | 20 retrieve results, 20 retrieve citations |
| SiliconFlow reranker | Passed | Tier-1, `qwen3-reranker-0.6b@siliconflow`, top_n 20 |
| DeepSeek answer | Passed | `answer.kind=answer`, non-empty answer |
| Citation validation | Passed | 7 validated answer citations |

Sanitized metrics:

```json
{
  "profile_answer_max_output_tokens": 1024,
  "embedded_chunk_count": 423,
  "qdrant_points_upserted": 423,
  "retrieve_result_count": 20,
  "retrieve_citation_count": 20,
  "reranker_vendor": "qwen3-reranker-0.6b@siliconflow",
  "reranker_top_n_returned": 20,
  "answer_model_id": "deepseek-v4-flash",
  "answer_kind": "answer",
  "answer_text_len": 445,
  "answer_citation_count": 7,
  "warnings": []
}
```

## Remaining Follow-Ups

1. Retrieval quality tuning remains separate: the ASKO query is answerable, but future evals should check that top evidence sections are the most operationally useful ones.
2. The parser still emits rotated-text warnings for the real PDFs; this does not block rebuild or answer generation, but operator-facing warning summarization can be improved later.
