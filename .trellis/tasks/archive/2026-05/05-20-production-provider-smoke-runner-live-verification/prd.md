# Production Provider Smoke Runner Live Verification

## Goal

Run the one-command production-provider smoke runner against local Docker Qdrant/MinIO and live SiliconFlow/DeepSeek providers, then record sanitized evidence.

## Requirements

- Use `scripts/run_production_provider_smoke.py` as the only smoke entry point.
- Use `examples/config/production-provider-verification.yaml` and the default ASKO W6564 manual.
- Keep provider secrets in environment variables only.
- Confirm the runner starts/verifies providers, ensures the bucket, resets Qdrant, and produces a passing smoke report.
- Commit only sanitized docs/task artifacts, never `.tmp` runtime reports or secret values.

## Acceptance Criteria

- [x] Runner exits 0 with live providers and local Docker services.
- [x] Runner summary shows required env, Docker providers, S3 bucket, and production-provider smoke passing.
- [x] Nested smoke report shows Qdrant point count equals graph node count and missing vectors are 0.
- [x] A docs report records only sanitized metrics and follow-up notes.

## Notes

- This is a live verification/docs task; code changes are not expected unless the runner exposes a product issue.
