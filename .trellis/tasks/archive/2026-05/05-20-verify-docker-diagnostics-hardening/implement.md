# Implementation Plan

1. Add bounded stdout/stderr capture to verify subprocess checks.
2. Add aggregation logic that downgrades Docker-start failure to warning only when S3 and nested smoke pass.
3. Add unit tests for Docker warning, check-only failure, and sanitized tails.
4. Update `docs/production-provider-smoke-runbook.md`.
5. Run focused tests plus sanitization checks, then commit and archive.
