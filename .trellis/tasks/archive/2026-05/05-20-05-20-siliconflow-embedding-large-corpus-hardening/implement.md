# Implementation Plan

## Steps

1. Replace placeholder task context entries with backend spec references.
2. Add sanitized batch diagnostic helpers to `HttpEmbedder`.
3. Add recursive split retry for failed multi-item HTTP batches.
4. Add unit tests for split retry, stable ordering, and safe failure detail.
5. Run focused tests, then the required unit/e2e suite.

## Validation

```bash
uv run pytest tests/unit/test_embedder_http.py -q
uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py -q
git diff --check
```

## Rollback

Revert the embedder and test changes. No data migration or persistent format change is involved.
