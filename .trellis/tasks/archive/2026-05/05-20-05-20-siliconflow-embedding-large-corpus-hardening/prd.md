# SiliconFlow embedding large corpus hardening

## Goal

Make HTTP embedding rebuilds diagnosable and more resilient for larger PDF-derived corpora, especially the SiliconFlow provider path used by the production-provider pilot.

## Requirements

- Preserve the existing OpenAI-compatible embedding contract and configuration shape.
- Keep API keys, raw document text, raw provider bodies, and embedding vectors out of errors, logs, reports, and tests.
- When an HTTP embedding batch fails, expose safe detail that helps operators act: endpoint, status/error type, batch size, text length bounds, total character count, and whether a retry split was attempted.
- Automatically split a failing multi-item HTTP embedding batch into smaller sub-batches before surfacing an error, so one oversized provider request does not fail the whole rebuild when smaller requests can succeed.
- Preserve embedding order and vector normalization semantics after sub-batch retries.
- Keep rebuild failure behavior unchanged: a final embedding failure still raises `EMBEDDING_FAILED` and must not replace the active KB.

## Acceptance Criteria

- [x] Unit tests cover successful fallback from a failed multi-item batch to smaller HTTP batches.
- [x] Unit tests cover safe diagnostic detail on final HTTP embedding failures without leaking raw text or secrets.
- [x] Existing HTTP embedder payload, endpoint override, dotenv key, missing key, and provider factory tests still pass.
- [x] Full unit/e2e test suite passes.

## Notes

- Follow-up from `docs/production-provider-e2e-pilot.md`: the small fixture passed with SiliconFlow embeddings, but real PDF-derived corpora failed with `EmbeddingError: Embedding API request failed`.
