# M16 Qdrant ANN Preselection

## Goal

Add an optional Qdrant-backed ANN preselection step for `/search` and CLI search so large KBs do not need to score every in-memory vector before WAVE-RAG propagation. Qdrant should become a candidate generator, not the final ranking engine: the served graph, anchor boosts, metadata filters, and WAVE propagation semantics must remain the source of truth for final result ordering.

## Background / Known Context

- M9 introduced Qdrant as a selectable vector persistence backend but explicitly deferred remote ANN search.
- M15 added safe Qdrant payloads and point-level incremental sync, so Qdrant collections now track build identity and chunk identity more faithfully across managed-library rebuilds.
- Current search flow loads the full vector matrix into memory and computes `vectors @ query_vec` inside `wave_search()`, then propagates over the full graph.
- `wave_search()` already accepts `eligible_node_ids`, so a preselected candidate set can constrain source selection and propagation without changing the caller-facing result shape.
- Search still needs deterministic behavior for filters, tie-breaking, anchors, and metadata boosts.
- Existing NPZ deployments and users without Qdrant configured must keep the current exact in-memory path.

## Requirements

### 1. Optional Candidate Preselection

- Add a config-controlled search mode that uses Qdrant ANN to preselect candidate node ids before WAVE search.
- Default behavior must remain the current exact in-memory scoring path unless the operator explicitly enables ANN preselection.
- The feature must only activate when `vector_store.provider=qdrant` and the KB is loaded successfully.

### 2. Preserve WAVE-RAG as Final Ranker

- Qdrant ANN must not become the final ranking output for `/search`.
- Final results must still be produced by local `wave_search()` over the loaded graph and in-memory vectors.
- ANN output should be used only to narrow:
  - source candidate ids
  - optionally the propagation eligibility set, if that can be done without breaking anchor/filter semantics

### 3. Filter and Anchor Compatibility

- Metadata filters (`manual_id`, `brand`, `product_category`, `product_model`, `language`, `tags`) must remain honored.
- If filters are present, candidate preselection must not produce results outside the filtered set.
- Anchor boosts and propagation boosts must keep working with ANN-enabled search.
- If an anchor target would be excluded by ANN candidate truncation, the design must define whether anchors are force-included or ANN is bypassed.

### 4. Deterministic Fallback and Safety

- If ANN preselection is unavailable, unsafe, or fails at request time, search must fall back to the current exact in-memory path rather than failing the request by default.
- Fallback reason should be visible in logs/metrics and, where appropriate, tracing attributes, but not require an API response shape break.
- Operators should be able to force exact search by config even when Qdrant is enabled.

### 5. Candidate Contract

- Define a bounded candidate count distinct from final `top_k`, for example `ann_candidate_k`.
- Candidate selection must be deterministic enough for tests when the fake client returns stable scores.
- The preselection contract should clarify whether it returns:
  - only source seeds for WAVE propagation
  - or a full eligible-node set for propagation and ranking

### 6. Observability

- Add low-cardinality reporting for:
  - ANN enabled/disabled
  - ANN outcome: used / fallback / bypassed
  - candidate count
- Do not log raw query text, high-cardinality source paths, or vectors.

### 7. Compatibility

- Preserve NPZ behavior completely.
- Preserve API and CLI response schemas except for additive metadata if truly useful.
- Do not require live Qdrant in the default test suite.
- Existing Qdrant collections synced by M15 should be sufficient; do not require a migration just to enable ANN candidate recall.

## Acceptance Criteria

- [ ] Config can enable or disable Qdrant ANN preselection independently of the default exact path.
- [ ] When enabled with Qdrant, search can obtain candidate node ids from Qdrant and still rank final results through local WAVE-RAG.
- [ ] Filtered searches remain filter-correct with ANN enabled.
- [ ] Anchor behavior remains compatible and explicitly tested under ANN-enabled search.
- [ ] Search falls back to exact in-memory behavior when ANN preselection is unavailable or fails.
- [ ] NPZ-backed search behavior remains unchanged.
- [ ] Tests cover fake-client ANN candidate retrieval, fallback behavior, filter compatibility, and ranking/response regression.
- [ ] README and backend spec document ANN preselection semantics, fallback behavior, and operator controls.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- Focused search, Qdrant, API, and CLI tests pass.
- `uv run pytest tests/ -q` passes.
- Operators can understand when ANN is active, bypassed, or falling back.
- Search semantics remain WAVE-RAG based rather than becoming remote ANN ranking.

## Out of Scope

- Replacing WAVE-RAG with pure Qdrant ranking.
- Distributed query fanout or multi-replica search coordination.
- Qdrant Cloud auth/config expansion unless implementation proves it necessary.
- Hybrid lexical/vector retrieval.
- Rewriting rebuild or persistence flows beyond what is needed to support query-time preselection.
- Non-Qdrant ANN backends in this milestone.

## Open Questions

- Should ANN constrain only initial source nodes, or the entire eligible propagation subgraph?
- Should anchors force-include their target nodes in the eligible set when ANN is enabled?
- Should ANN fallback be silent to clients, or should additive response/debug metadata expose that the exact path was used?
