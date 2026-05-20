# Implementation Plan

1. Recreate the provider verification real PDF KB if local `.tmp` state is missing.
2. Run `/answer` through `TestClient` with the merged profile default budget.
3. Inspect the plan log for reranker status.
4. Write a sanitized report under `docs/deepseek-citation-live-verification.md`.
5. Run focused answer tests and full unit/e2e tests.
