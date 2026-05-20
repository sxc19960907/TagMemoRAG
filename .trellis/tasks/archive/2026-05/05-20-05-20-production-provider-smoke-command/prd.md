# Production Provider Smoke Command

## Goal

Provide one repeatable command that runs the real production-provider local smoke path after Qdrant and MinIO are started locally and SiliconFlow/DeepSeek keys are supplied via environment variables.

## Requirements

- Add a CLI command for production-provider smoke verification.
- Reuse existing config validation, provider probe, manual bulk import, registry blob verification, manual-library rebuild, Qdrant inspection, and `/answer` runtime paths.
- Support local manual inputs with sidecar metadata discovery so a user can run one command against one or more product manuals.
- Emit JSON or Markdown reports that are useful for rollout records.
- Keep reports sanitized: no raw answer text, document snippets, vectors, provider response bodies, or secrets.
- Return a non-zero exit code when any required stage fails.

## Acceptance Criteria

- [x] CLI exposes `production-provider smoke` with config, KB, manual, metadata, workdir, output, format, and question options.
- [x] Report includes stage statuses for config, provider readiness, import, blob verification, rebuild, Qdrant, reranker evidence, and answer smoke.
- [x] Report includes counts and IDs safe for operators: import counts, checked blob count, embedded chunk count, Qdrant point/missing-vector counts, answer kind/text length/citation count, warnings, and next steps.
- [x] Unit tests cover report serialization, sidecar metadata discovery, answer sanitization, and CLI argument wiring without network calls.

## Notes

- Live verification remains operator-triggered because it requires Docker services and external providers.
