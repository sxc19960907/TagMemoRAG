# Unified Verify CLI Live Verification

## Goal

Run the merged `production-provider verify` unified CLI against the local Docker provider stack and live SiliconFlow/DeepSeek providers, then record sanitized evidence.

## Requirements

- Use `python -m tagmemorag production-provider verify` as the verification entry point.
- Run at least the `--level smoke` live path.
- Run `--level pilot` if the live provider cost/runtime remains reasonable after smoke passes; otherwise document why it was deferred.
- Keep all provider secrets in environment variables only.
- Commit only sanitized docs/task artifacts, never `.tmp` reports or secret values.

## Acceptance Criteria

- [x] Unified verify smoke exits 0 with live providers and already-running local Docker services.
- [x] Verify summary shows required env, S3 bucket, and nested smoke passing, with Docker startup explicitly skipped after the default path exposed a Docker diagnostic follow-up.
- [x] Nested smoke report shows Qdrant point count equals graph node count and missing vectors are 0.
- [x] Pilot path is either run successfully or explicitly deferred with a concrete reason.
- [x] A docs report records only sanitized metrics and follow-up notes.

## Notes

- This is a live verification/docs task; code changes are not expected unless the unified CLI exposes a product issue.
