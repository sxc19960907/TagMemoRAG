# Provider Live Probe — Design

## Boundary

This task adds an operator CLI probe for live external services. It is additive and explicit:

```bash
tagmemorag provider probe --config config.yaml --embedding
tagmemorag provider probe --config config.yaml --all
```

It does not change server startup, readiness endpoints, config validation, provider runtime behavior, or storage schemas.

## Report Contract

```json
{
  "schema_version": "provider_probe.v1",
  "status": "passed",
  "probes": [
    {
      "name": "embedding",
      "status": "passed",
      "detail": {"provider": "http", "model": "Qwen/..."}
    }
  ]
}
```

Statuses:

- `passed`: live call succeeded and returned minimal expected shape
- `warning`: live call was not possible because optional dependency is missing or another non-fatal probe limitation applies
- `failed`: explicit probe failed or configured provider returned an error
- `skipped`: provider not configured/enabled and probe was selected via `--all`

Aggregate:

- `failed` if any probe failed
- `warning` if no failures and any probe warned
- `skipped` if every probe skipped
- otherwise `passed`

Exit code:

- `0` for `passed`, `warning`, or `skipped`
- `1` for `failed`

## Safety

Probe output is bounded and low-sensitive. Allowed details:

- provider name
- model id
- env var name, never value
- endpoint host/path if already configured, not Authorization
- response status code when available
- dependency name
- count/shape booleans, not raw vectors or text

Disallowed:

- secret values
- request/response bodies
- generated answer text
- embedding vectors
- raw document text
- S3 object keys beyond configured bucket/prefix names already in config

## Probe Shape

- Embedding: only when `model.provider=http`; use `create_embedder()` and `encode_batch(["readiness probe"])`; assert one vector and configured/nonzero dimension. Local/hash providers skip under `--all` and fail only when `--embedding` explicitly asks for a remote probe that is not configured.
- Answer: only when `answer.enabled=true` and `answer.provider=openai_compatible`; use `OpenAICompatibleAnswerGenerator` with a tiny `AnswerRequestContext`; assert a parsed answer object returns without printing text.
- Reranker: only when `reranker.enabled=true` and `reranker.provider=siliconflow`; call `SFQwen3Reranker.rerank()` with one short query and two short docs; assert outcome object returns.
- Qdrant: only when `vector_store.provider=qdrant`; call collection info through `inspect_qdrant()` or direct client boundary. Missing collection is a failed live probe if explicitly selected and a warning/failure under `--all` depending on config; this task will treat client errors as `failed` for configured Qdrant.
- S3: only when `manual_library.blob_backend=s3`; construct the configured client and call `head_bucket(Bucket=...)`.

## Test Strategy

All tests are fake/monkeypatched; default test runs must not perform network access. Probe functions should accept optional dependency/client factories where useful, or tests can monkeypatch module-level client classes/functions.

## Rollback

Revert the provider probe module, CLI parser branch, tests, and docs. No persistent data migration is involved.
