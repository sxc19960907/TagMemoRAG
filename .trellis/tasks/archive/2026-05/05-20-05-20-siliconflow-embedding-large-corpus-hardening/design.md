# SiliconFlow Embedding Large Corpus Hardening Design

## Boundary

The change is limited to the HTTP embedding client and focused tests. It does not change provider configuration, rebuild orchestration, Qdrant sync, PDF parsing, or embedding model identity.

## Data Flow

`build_kb` and rebuild paths call `embedder.encode_batch(texts)`. For `provider=http`, `HttpEmbedder.encode_batch` splits the input by configured `batch_size` and delegates each slice to the OpenAI-compatible embedding endpoint.

The hardened flow keeps this public shape:

1. Attempt the configured batch.
2. If a multi-item batch fails, retry by recursively splitting it into halves.
3. If a single-item batch fails, raise `EmbeddingError` with sanitized diagnostic detail.
4. Concatenate all successful sub-batches in the original order.
5. Normalize the final matrix when configured.

## Sanitized Diagnostics

HTTP embedding failures may include:

- `endpoint`
- `status_code` for HTTP failures
- `error_type` for network/timeout/JSON failures
- `batch_size`
- `min_text_chars`
- `max_text_chars`
- `total_text_chars`
- `split_attempted`

They must not include raw text, request body, Authorization headers, API key values, full provider error bodies, vectors, or source paths.

## Compatibility

No new settings are required. The fallback is always enabled for HTTP multi-item batches because it only activates after a provider request fails. Existing `model.batch_size` remains the maximum request size.
