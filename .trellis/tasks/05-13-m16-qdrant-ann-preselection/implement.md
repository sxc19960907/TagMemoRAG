# implement.md - M16 Qdrant ANN Preselection

## Implementation Checklist

- [x] Read backend specs with `trellis-before-dev` before coding.
- [x] Review current search orchestration, `wave_search()`, and Qdrant backend query capabilities.
- [x] Add config for ANN preselection opt-in and candidate count.
- [x] Add a Qdrant backend query helper for candidate node-id retrieval.
- [x] Decide and implement the orchestration point that chooses exact vs ANN-assisted search.
- [x] Preserve local filter handling and define fallback behavior when ANN candidates are insufficient.
- [x] Preserve or explicitly merge anchor-required nodes into ANN candidate eligibility.
- [x] Keep final ranking in local WAVE-RAG and avoid using Qdrant scores as final result scores.
- [x] Add low-cardinality logging/metrics/tracing fields for ANN used/bypassed/fallback.
- [x] Update README and backend spec documentation.

## Validation

Focused tests:

- `uv run pytest tests/unit/test_storage_state.py -q`
- `uv run pytest tests/unit/test_api.py -q`
- `uv run pytest tests/unit/test_cli.py -q`
- `uv run pytest tests/unit/test_graph_wave.py -q`

Add tests for:

- fake Qdrant client returns deterministic ANN candidate ids
- ANN-enabled search still returns WAVE-ranked results
- metadata filters remain correct with ANN enabled
- anchor-sensitive queries preserve anchor behavior
- request-time Qdrant ANN failure falls back to exact local search
- NPZ provider regression

Final check:

- `uv run pytest tests/ -q`

## Review Gates

- Confirm WAVE-RAG remains the final ranking engine.
- Confirm ANN cannot silently bypass filters or anchors.
- Confirm fallback behavior is deterministic and operator-visible.
- Confirm no raw query text, vectors, or high-cardinality values are added to logs/metrics.

## Rollback Points

- If filter-safe ANN is too risky, first ship ANN only for unfiltered searches and force exact path otherwise.
- If anchor handling proves fragile, force exact path whenever anchors are present.
- If query-time Qdrant latency is unstable, keep the config and default it off until more tuning lands.
