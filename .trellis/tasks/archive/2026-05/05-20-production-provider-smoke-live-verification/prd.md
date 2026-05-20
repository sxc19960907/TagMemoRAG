# Production Provider Smoke Live Verification

## Goal

Run the merged `production-provider smoke` command against local Qdrant/MinIO and live SiliconFlow/DeepSeek providers, then record a sanitized verification report.

## Requirements

- Use `examples/config/production-provider-verification.yaml`.
- Use local Docker providers for Qdrant and MinIO.
- Use SiliconFlow for embedding and reranker, and DeepSeek for answer generation.
- Import at least one real product manual PDF with sidecar metadata.
- Produce a repo documentation report with only sanitized operational metrics.
- Do not commit provider keys, raw answer text, retrieved snippets, vectors, or provider response bodies.

## Acceptance Criteria

- [x] Docker provider services are reachable before smoke execution.
- [x] Smoke command runs and records stage statuses for config, provider probe, import, blob verification, rebuild, Qdrant, reranker evidence, and answer.
- [x] A docs report captures command, environment shape, sanitized results, failures if any, and next steps.
- [x] Any generated `.tmp/` runtime artifacts remain uncommitted.

## Notes

- This is a verification/docs task; implementation changes are not expected unless the live run exposes a product bug.
