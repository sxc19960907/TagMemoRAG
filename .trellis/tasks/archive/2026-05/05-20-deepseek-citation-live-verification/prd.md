# DeepSeek citation live verification

## Goal

Verify the merged DeepSeek budget and text-citation extraction changes against the real ASKO/HISENSE PDF `/answer` path.

## Requirements

- Use `examples/config/production-provider-verification.yaml`.
- Keep provider keys in process environment only.
- Rebuild or reuse the real PDF KB as needed.
- Capture only sanitized metrics: answer kind, text length, citation counts, warnings, reranker status, and retrieval counts.
- Do not commit raw answer text, raw retrieved snippets, provider responses, vectors, or secrets.

## Acceptance Criteria

- [x] Real PDF KB rebuild is available with Qdrant points aligned to graph nodes.
- [x] `/answer` succeeds using the profile default answer budget.
- [x] The report records whether valid citations are now produced.
- [x] If citations remain zero, the report identifies the next concrete fix.
- [x] Focused answer tests and full unit/e2e tests pass.
