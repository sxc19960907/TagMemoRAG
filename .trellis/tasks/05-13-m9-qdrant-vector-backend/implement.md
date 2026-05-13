# implement.md - M9 Qdrant Vector Backend

## Checklist

- [x] Read backend specs and M9 artifacts.
- [x] Add vector store config model and YAML docs.
- [x] Add vector store factory used by `save_kb()` and `load_kb()`.
- [x] Add `QdrantVectorStore` with lazy import and fake-client-testable constructor.
- [x] Preserve NPZ behavior as default.
- [x] Add tests for config, factory, Qdrant vector operations, and build/save/load routing.
- [x] Update README with Qdrant setup.
- [x] Run focused tests and full test suite.
