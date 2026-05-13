# M9 Qdrant vector backend

## Goal

Add Qdrant as a selectable vector persistence backend while preserving the existing WAVE-RAG graph flow.

## Requirements

- Add a `vector_store` config section with provider `npz` by default and optional `qdrant`.
- Keep existing local `data/{kb_name}/graph.json`, `anchors.json`, and `meta.json` behavior.
- When `vector_store.provider=npz`, preserve existing `vectors.npz` persistence and tests.
- When `vector_store.provider=qdrant`, persist chunk embeddings in a Qdrant collection keyed by KB and node id.
- Load Qdrant vectors back into memory in node-id order so WAVE-RAG graph propagation remains unchanged.
- Provide clear `INVALID_CONFIG` or `STORAGE_LOAD_FAILED` errors for missing client dependency, invalid dimensions, or Qdrant connectivity/storage failures.
- Avoid requiring a live Qdrant service for the normal test suite; unit tests may use a fake client.
- Document local Qdrant usage and configuration.

## Acceptance Criteria

- [ ] Default NPZ behavior remains backward compatible.
- [ ] Qdrant backend can save/load vectors for a KB and preserve deterministic node-id ordering.
- [ ] `save_kb()` and `load_kb()` route vector persistence through the selected backend.
- [ ] Config supports env overrides for vector backend selection and Qdrant URL/collection prefix.
- [ ] Tests cover NPZ factory behavior, Qdrant save/load/search/get via a fake client, and config parsing.
- [ ] Full test suite passes.

## Notes

- Qdrant is introduced as vector persistence first. Replacing WAVE-RAG candidate generation with remote ANN search is deferred.
