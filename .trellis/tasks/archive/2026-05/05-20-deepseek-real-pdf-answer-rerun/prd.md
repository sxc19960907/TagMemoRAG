# DeepSeek real PDF answer rerun

## Goal

Validate `/answer` on the real ASKO/HISENSE PDF knowledge base using the production-provider profile: SiliconFlow embeddings/reranker, Qdrant vectors, MinIO blobs, and DeepSeek answer generation.

## Requirements

- Use `examples/config/production-provider-verification.yaml`.
- Keep DeepSeek and SiliconFlow keys in process environment only; do not persist secret values.
- Reuse or rebuild the real PDF KB as needed.
- Capture sanitized evidence: retrieve result counts, reranker status, answer kind/provider/model, answer text length, citation count, warnings, and budget behavior.
- Do not commit raw answer text, raw retrieved snippets, API keys, Authorization headers, raw provider responses, or vectors.

## Acceptance Criteria

- [x] Real PDF KB is available with Qdrant point count aligned to graph nodes.
- [x] `/answer` is exercised against real PDF content with DeepSeek.
- [x] Report records whether answer generation succeeds with a sufficient token budget.
- [x] Report records citation compliance and remaining gaps.
- [x] No secrets or raw answer/retrieval text are committed.
