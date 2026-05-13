# design.md - M16 Qdrant ANN Preselection

## Scope

M16 adds an optional query-time Qdrant ANN preselection step ahead of local WAVE-RAG scoring. The goal is to shrink the number of nodes considered during source selection without changing the final search contract: graph propagation, anchors, metadata boosts, and result serialization remain local behaviors.

## Current Search Flow

```text
query
  -> embed query
  -> filter eligible graph node ids locally
  -> exact vector scoring over in-memory matrix
  -> choose source_k seeds
  -> WAVE propagation over eligible graph
  -> top_k results
```

Today, even Qdrant-backed KBs still load vectors into memory and use exact local dot-product scoring for every eligible node.

## Proposed Search Flow

```text
query
  -> embed query
  -> normalize filters
  -> decide strategy:
       exact_local
       ann_preselect_then_wave
  -> if ANN:
       ask Qdrant for top ann_candidate_k node ids
       intersect with local filter-eligible ids
       merge anchor-required ids if needed
  -> run local wave_search(query_vec, ..., eligible_node_ids=...)
  -> return normal results
```

The exact path remains the compatibility baseline. ANN is an optimization layer, not a semantic replacement.

## Recommended MVP Contract

### Config

Add a small search config section, for example:

```yaml
search:
  ann_preselect_enabled: false
  ann_candidate_k: 64
  ann_force_exact_on_filters: false
```

Suggested semantics:

- `ann_preselect_enabled=false` keeps the current exact path.
- `ann_candidate_k` bounds the candidate pool returned by Qdrant before WAVE.
- `ann_force_exact_on_filters=true` is a conservative escape hatch if filter-aware ANN turns out risky in the first rollout.

If adding fields directly under `search` feels crowded, a nested `search.ann.*` block is also reasonable. The important part is explicit opt-in and deterministic defaults.

### Candidate Strategy

Recommended MVP: ANN returns an eligible-node set for local WAVE, not final ranked results.

That means:

1. Qdrant returns candidate node ids with approximate similarity scores.
2. The caller discards Qdrant scores after candidate selection.
3. Local `wave_search()` recomputes exact dot-product values from in-memory vectors and uses normal propagation/ranking logic.

This keeps the ranking surface stable and avoids mixing approximate Qdrant scores with wave amplitudes.

### Filters

Recommended MVP behavior:

- Compute local `filter_node_ids()` first.
- If no filters are present, Qdrant ANN can search the whole KB collection.
- If filters are present, use the local eligible set as a post-filter on ANN candidates.
- If too few candidates survive the filter, fall back to exact local search rather than risk false negatives.

This is conservative but easy to reason about. A later task can add payload-filtered Qdrant ANN once payload coverage and performance are proven.

### Anchors

Recommended MVP behavior:

- If anchor node ids exist for the current KB and are eligible under filters, union them into the ANN-derived eligible set.
- If this union would still leave too small a candidate set for safe propagation, fall back to exact local search.

This avoids the bad case where ANN accidentally excludes the very node an anchor is meant to boost.

## API / CLI Surface

No new endpoint is required. Existing search surfaces should remain stable:

- `POST /search`
- `python -m tagmemorag search`

Additive debug metadata is acceptable only if it stays optional and low-noise. Example:

```json
{
  "meta": {
    "search_strategy": "ann_preselect_then_wave",
    "ann_candidate_count": 64,
    "ann_fallback_reason": ""
  }
}
```

If response metadata feels too user-facing for MVP, keep this only in logs/traces/metrics.

## Qdrant Store Contract

MVP likely needs one new query method on the concrete Qdrant backend, such as:

```python
QdrantVectorStore.search_ids(query_vec, k) -> list[int]
```

or a slightly richer internal result:

```python
QdrantVectorStore.search_candidates(query_vec, k) -> list[tuple[int, float]]
```

The latter is more flexible, but the scores should remain advisory only for debugging; local WAVE should still use in-memory exact scores.

NPZ does not need to implement this. Search orchestration can simply branch on `vector_store.provider`.

## Fallback Rules

Use the exact local path when:

- `vector_store.provider != qdrant`
- ANN config is disabled
- Qdrant client/search capability is unavailable
- the KB is loaded from NPZ
- filters prune ANN candidates too aggressively
- anchors require nodes not safely represented in ANN candidates
- Qdrant request fails or returns malformed ids

Fallback should be logged and traced with a structured reason, for example:

- `ann_disabled`
- `provider_not_qdrant`
- `ann_query_failed`
- `filtered_candidates_too_small`
- `anchor_force_exact`
- `candidate_ids_invalid`

## Testing Strategy

Fake-client unit tests should cover:

- candidate ids returned in stable order
- ANN-enabled search still returns local WAVE-ranked results
- filtered search stays correct
- anchor-heavy search keeps anchor semantics
- fallback to exact path when fake Qdrant fails
- NPZ regression

API/CLI tests should verify the feature does not alter response schema compatibility unless additive metadata is explicitly introduced.

## Rollout / Rollback

- Ship behind explicit config opt-in.
- Keep exact local search as the default.
- Operators can disable ANN instantly by config if query quality or failure behavior is suspicious.
- If rollout reveals semantic drift, keep Qdrant for persistence and revert search to exact local mode without undoing M9/M15.

## Risks

- ANN truncation can hide nodes that exact WAVE would have used as strong seeds.
- Post-filtering after ANN can under-represent narrow metadata slices.
- Anchor-driven queries may be more sensitive to candidate truncation than plain semantic similarity queries.
- If `ann_candidate_k` is too low, recall loss may look like ranking drift rather than obvious failure.
