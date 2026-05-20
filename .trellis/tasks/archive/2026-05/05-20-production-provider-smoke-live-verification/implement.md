# Implementation Plan

1. Start or verify local provider Docker services.
2. Ensure the MinIO bucket exists for the verification profile.
3. Run `production-provider smoke` against a real PDF manual using env-only provider credentials.
4. Inspect the sanitized report and add `docs/production-provider-smoke-live-verification.md`.
5. Run a focused non-network verification if code/docs changed, then archive and commit.
