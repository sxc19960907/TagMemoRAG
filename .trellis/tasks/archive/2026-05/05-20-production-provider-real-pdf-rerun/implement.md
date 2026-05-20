# Implementation Plan

1. Start from clean `master` and create an isolated run directory under `.tmp/production-provider-rerun`.
2. Ensure local MinIO bucket and Qdrant are reachable.
3. Import ASKO W6564 and HISENSE BSA5221 PDFs into the provider verification registry/blob profile.
4. Run full managed-library rebuild with SiliconFlow embeddings and Qdrant vector storage.
5. Inspect registry blob verification and Qdrant state.
6. Write a sanitized report under `docs/production-provider-real-pdf-rerun.md`.

## Validation Commands

```bash
uv run python -m tagmemorag manual-bulk import ...
uv run python -m tagmemorag manual-library registry verify-blobs ...
uv run python -m tagmemorag manual-library rebuild ...
uv run python -m tagmemorag qdrant inspect ...
```
