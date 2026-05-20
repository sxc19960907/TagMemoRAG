# T1.5 IndexGeneration derivatives isolation

## Goal

Close the T1 gap where generation core artifacts are isolated under `gN/`, but
derived artifacts still write to `_global`. T1.5 adds generation-aware derivative
paths while preserving legacy `_global` behavior for existing active builds.

## Requirements

- Keep legacy full/incremental rebuild behavior compatible.
- Add generation-aware paths for EPA basis, tag co-occurrence, tag intrinsic
  residuals, and tag embeddings where practical.
- Shadow/generation builds should be able to write/read derivative artifacts
  inside the target generation root via `KbPaths`.
- Existing `_global` paths remain fallback-compatible for readers.
- Fail-soft rebuild semantics remain unchanged.
- Tests cover legacy path stability and generation path routing.

## Acceptance Criteria

- [x] `KbPaths` derivative path tests remain green.
- [x] `tag_cooccurrence` can save/load from a generation-aware path.
- [x] `tag_rebuild.sync_rebuild_tags()` can accept generation paths.
- [x] `epa_basis.retrain_report()` can accept generation-aware paths.
- [x] Shadow build or generation-oriented rebuild code can pass `KbPaths`.
- [x] Legacy tests using `_global` still pass.
- [x] Focused derivative tests and full unit suite pass.
