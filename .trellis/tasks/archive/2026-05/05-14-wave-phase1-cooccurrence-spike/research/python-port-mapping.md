# Source → Python Port Mapping

> Concrete plan for translating `TagMemoEngine.applyTagBoost` + the directed
> co-occurrence matrix into TagMemoRAG. Reads alongside the two source-* docs.

## Module placement

| Source state / behaviour | Target Python module | Rationale |
|---|---|---|
| `tagCooccurrenceMatrix` (Map<id, Map<id, w>>) builder | new `src/tagmemorag/tag_cooccurrence.py` | Mirrors Phase 0's `tag_store.py` / `tag_embedder.py` pattern: one focused module per data asset |
| Persisted matrix file | `data/_global/tag_cooccurrence.npz` (per-KB key prefix or per-KB file) | Use existing atomic-write pattern from `epa_basis.py`. Per-KB file is simpler than packing many KBs in one npz |
| Spike propagation | new `src/tagmemorag/wave_tag_spike.py` | Pure algorithm; depends on `tag_store` for vectors and `tag_cooccurrence` for the matrix |
| Boost integration into search | extend `src/tagmemorag/search_runtime.execute_search` | Single integration point — query vector goes in, modified vector before `wave_search`. Keeps existing flow |
| Config | extend `src/tagmemorag/config.py` `WavePhase0Config` → also add `wave_phase1` block | Same pattern as Phase 0; `wave_phase0` keeps EPA settings, `wave_phase1` keeps spike + cooccurrence settings |
| Lifecycle: build matrix on rebuild | extend `src/tagmemorag/tag_rebuild.sync_rebuild_tags` | Already the rebuild-end synthesis point; add cooccurrence rebuild after EPA retrain |
| Observability | extend `observability/metrics.py` | Add 3 metrics: `tag_cooccurrence_edges_total{kb_name}`, `tag_cooccurrence_rebuild_duration_seconds{kb_name}`, `tag_spike_propagations_total{kb_name, outcome}` |
| Search behaviour gate | new `wave_phase1.spike_enabled` config flag | Defaults true; can flip false to revert search behaviour without removing data |

## Data structures

### Co-occurrence matrix in Python

Source uses nested `Map`. Python equivalents and tradeoffs:

| Choice | Pros | Cons |
|---|---|---|
| `dict[int, dict[int, float]]` | Direct port, sparse, easy to unit-test | Loop overhead in pure Python (no numpy) |
| `scipy.sparse.csr_matrix(N, N, dtype=f32)` + `tag_id ↔ row` map | Vectorised, lowest memory at scale | Extra index map; csr is poor for incremental updates (we don't need that — full rebuild) |
| `dict` of `numpy.array` rows | Hybrid: vectorised neighbour iteration | Double bookkeeping |

**Decision**: `dict[int, dict[int, float]]` for Phase 1. Fixture has ≤30 edges; production tag counts unlikely to exceed 10⁴ in this codebase's lifetime. If profile shows hot path, swap to scipy.sparse later.

### Persisted matrix format

```
data/_global/tag_cooccurrence.npz  (single file, per-KB partitioned)
  schema_version: int32
  built_at:       str (ISO)
  kbs:            list[str]                       # ordered KB names
  kb_offsets:     int32[len(kbs)+1]               # CSR-like: kbs[i]'s edges live in [offsets[i], offsets[i+1])
  source_ids:     int64[total_edges]
  target_ids:     int64[total_edges]
  weights:        float32[total_edges]
```

OR simpler: one npz per KB:

```
data/_global/tag_cooccurrence/{kb_name}.npz
  source_ids: int64[E]
  target_ids: int64[E]
  weights:    float32[E]
  meta_built_at: str
  meta_schema_version: int32
```

**Decision**: per-KB npz under `data/_global/tag_cooccurrence/`. Reasons:
- Atomic-write per KB matches existing rebuild-per-KB cadence.
- A KB with no tags simply has no file (instead of empty rows in a global file).
- Schema migration is per-KB, can roll forward independently.

Atomic write: tmp → fsync → replace → fsync(dir), reusing the helper from `epa_basis.save_epa_basis`.

### EPA & ResidualPyramid surrogates

Phase 1 does NOT depend on a real ResidualPyramid. Substitute:

```python
def _seed_tags_from_query(query_vec, kb_name, conn, *, top_k: int = 8, min_similarity: float = 0.3):
    """Return top-K tags by cosine similarity to query, with adjusted weights."""
    rows = list(iter_canonical_tags_with_vectors(conn, kb_name=kb_name))
    if not rows:
        return []
    sims = []
    for tag, vec_bytes, _dim in rows:
        if vec_bytes is None:
            continue
        v = np.frombuffer(vec_bytes, dtype=np.float32)
        sim = float(np.dot(query_vec, v) / (np.linalg.norm(query_vec) * np.linalg.norm(v) + 1e-12))
        if sim >= min_similarity:
            sims.append((tag, sim))
    sims.sort(key=lambda x: -x[1])
    return sims[:top_k]
```

The EPA `project()` is reused as-is for `logicDepth` (already implemented in Phase 0 `epa_projector.py`). With cold-start basis, `logicDepth ≈ 1 - log2(8)/log2(8) = 0` for uniform projection. That's fine — `dynamicBoostFactor = max(0.3, logicDepth)` keeps the boost from collapsing.

## Lifecycle integration

### Rebuild pipeline

`incremental_rebuild` and `state.build_kb` both end with `tag_rebuild.sync_rebuild_tags`. Insert co-occurrence rebuild as the final step:

```python
# tag_rebuild.sync_rebuild_tags  (existing, extended)
def sync_rebuild_tags(kb_name, cfg, *, manual_tags_by_id, embedder, ...):
    registry = create_registry(...)
    with registry.connection() as conn:
        with conn:
            # ... existing manual_tags upsert + orphan cleanup ...
        # ... existing tag embedding ...
    # Phase 0: EPA retrain (existing)
    epa_report = retrain_report(cfg)
    # Phase 1: NEW
    cooc_report = build_cooccurrence_for_kb(kb_name, cfg)  # also writes the npz
    return TagRebuildReport(
        ...,
        tag_cooccurrence_edges=cooc_report.edges,
        tag_cooccurrence_error=cooc_report.error,
    )
```

`build_cooccurrence_for_kb` reads `manual_tags` for that kb_name, runs the same algorithm as the source `buildDirectedCooccurrenceMatrix` step 2 + step 3, atomically writes the npz, and returns counts.

### Search pipeline

`search_runtime.execute_search` is the single integration point. Insert tag-boost as a transformation on `query_vec` before `wave_search`:

```python
def execute_search(*, state, query_vec, settings, top_k, ..., query_text=""):
    # ... existing lexical + ANN preselect ...
    if settings.wave_phase1.spike_enabled and tag_boost_available(state, settings):
        boosted_vec, boost_info = apply_tag_boost(
            query_vec=query_vec,
            kb_name=state.kb_name,
            settings=settings,
            base_tag_boost=settings.search.tag_boost,
        )
        query_vec = boosted_vec
    # ... existing wave_search call ...
    return SearchExecution(...)
```

Loaders for matrix/EPA basis must be cheap-or-cached, since `execute_search` runs per-query:

```python
# wave_tag_spike.py
@functools.lru_cache(maxsize=8)
def _load_cooccurrence_matrix(kb_name: str, mtime: float) -> dict[int, dict[int, float]]:
    """Cache by (kb_name, mtime). Bust whenever the npz file is rewritten."""
    ...
```

`mtime` parameter forces cache invalidation when the file is rewritten (rebuild path).

## Behaviour gates

Existing knobs that interact with Phase 1:

| Knob | Current behaviour | Phase 1 behaviour |
|---|---|---|
| `search.tag_boost` (default 0.03) | Tag-aware boost in `wave_searcher` (additive bonus on tag-matched chunks) | **Keep AND repurpose**: feed into `apply_tag_boost` as `base_tag_boost`. The query-vector blend replaces the chunk-side bonus. The chunk-side boost in `wave_searcher` is disabled when spike_enabled |
| `search.metadata_field_boost` | Boost on chunks whose metadata fields match query terms | Unchanged |
| `search.lexical_*` | Lexical co-ranking | Unchanged |
| `wave_phase0.epa_basis_enabled` | Master switch for EPA training | Unchanged. If false, `apply_tag_boost` falls back to `dynamicBoostFactor = 1.0` |
| **NEW** `wave_phase1.spike_enabled` | — | Master switch for query-vector boost. False ⇒ `execute_search` skips `apply_tag_boost` |
| **NEW** `wave_phase1.cooccurrence_enabled` | — | Master switch for matrix rebuild. False ⇒ `tag_rebuild.sync_rebuild_tags` skips the build step. Allows test cases that need a deterministic empty matrix |
| **NEW** `wave_phase1.spike_max_hops` etc. | — | All the spike-tuning constants from source ([4.5] section) |

## Compatibility & test strategy

- **AC6 byte-equality test from Phase 0** (`test_search_baseline_invariance`) **will fail** when `wave_phase1.spike_enabled = true`. This is expected — Phase 1 is the deliberate first time search reads tag tables.
- **New regression contract**: the eval suites + baseline (Phase 1 prerequisite that just landed) become the protective layer. Phase 1 must update `tests/fixtures/eval/baselines/hashing.json` after carefully reviewing the metric deltas. README's `eval-baseline-workflow.md` already covers the review flow.
- The two-mode test (spike on / spike off) should both pass:
  - `spike_enabled=false` ⇒ identical to current master
  - `spike_enabled=true` ⇒ baseline-2% threshold against new baseline

## Suggested file structure

```
src/tagmemorag/
  tag_cooccurrence.py           # build + load + save matrix
  wave_tag_spike.py             # apply_tag_boost + spike propagation
  config.py                     # add WavePhase1Config

tests/unit/
  test_tag_cooccurrence.py      # builder edge cases (n<2, n>100, legacy fallback, direction)
  test_wave_tag_spike.py        # propagation algorithm, hop cap, wormhole gate, energy aggregation
  test_apply_tag_boost.py       # full end-to-end including EPA + dedup + alpha-blend

tests/integration/ or e2e/
  test_phase1_search_with_spike.py  # wires search_runtime + state + cooccurrence
```

The split keeps the **algorithm** (wave_tag_spike) testable without I/O, and the **integration** (search_runtime change) tested via a minimal fixture KB.

## Known compatibility issues to call out in PRD

1. **AC6 byte-equality is broken on purpose.** Phase 1 PRD must explicitly retire the Phase 0 invariant (AC6 of Phase 0 said "no behaviour change"). The eval suites + baseline take its place.
2. **Two embedder regimes diverge.** Hashing dim=64 vs SiliconFlow dim=384 will produce very different EPA `logicDepth` and tag-cosine seeds. Both baselines must be refreshed; CI uses hashing.
3. **EPA cold-start makes `dynamicBoostFactor` mostly inert.** With logicDepth near zero on cold-start, `dynamicBoostFactor ≈ activationMultiplier ≈ 0.5` after clamping. The boost is real but small until EPA is trained on enough tags. That's by design — Phase 0 D2 anticipated this.
4. **Existing `tag_boost` chunk-side bonus.** Disable when spike is on, OR keep both? **Recommend disable** to avoid double-counting; expose a fallback `wave_phase1.legacy_chunk_tag_boost = false` so it can be flipped if quality regresses unexpectedly.

## Migration / rollback

```bash
# enable Phase 1
edit config.yaml: wave_phase1.spike_enabled: true
# rollback (without removing files):
edit config.yaml: wave_phase1.spike_enabled: false
# rollback (full data wipe):
rm -rf data/_global/tag_cooccurrence/
```

Co-occurrence file deletion does not break search — `apply_tag_boost` short-circuits when matrix is empty, returning the original query vector verbatim.
