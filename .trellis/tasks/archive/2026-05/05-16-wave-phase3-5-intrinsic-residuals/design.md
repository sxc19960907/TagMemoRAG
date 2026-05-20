# Technical Design

## Data Flow

1. Rebuild updates manual tag rows and dirty tag embeddings in `manual_registry.sqlite3`.
2. `_rebuild_cooccurrence` builds the directed cooccurrence NPZ for the KB.
3. `_rebuild_intrinsic_residuals` loads the freshly rebuilt cooc matrix and calls `train_intrinsic_residuals_for_kb`.
4. Training reads tag vectors from `tags.vector`, selects each tag's Top-N cooc neighbors from out+in edges, computes normalized residual energy, and upserts `tag_intrinsic_residuals`.
5. Online tag boost only consumes residuals when `wave_phase1.intrinsic_residuals_enabled=true`.

## Contracts

- Config:
  - `wave_phase1.intrinsic_residuals_enabled: bool = False`
  - `wave_phase1.intrinsic_residual_top_n: int | None = None`; `None` means reuse `pyramid_top_k`.
- Training:
  - Neighbor set = outgoing neighbors plus incoming neighbors. If both directions exist, use max weight for sorting.
  - Top-N ordering = weight desc, tag id asc.
  - Formula = `||tag_vector - projection(tag_vector, neighbor_basis)||^2 / ||tag_vector||^2`.
  - Missing / zero vector / no basis fallback = `1.0`; stored values are clamped to `[0.0, 1.0]`.
- Rebuild:
  - Producer always runs after cooc when phase1+cooc are enabled.
  - Training exceptions are converted to `tag_intrinsic_residual_error` and do not fail graph rebuild.
- Online:
  - Flag off keeps residual map absent, so current behavior is byte-compatible.
  - Flag on loads residuals from the registry. Missing tag ids use `1.0`.
  - Wormhole gets `residuals=` in `propagate`.
  - Pyramid candidate score uses `cosine * residual_energy`; returned similarity remains raw cosine for downstream math.

## Observability

- `tagmemorag_tag_intrinsic_residual_missing_total{kb_name,consumer}` increments on enabled-on fallback.
- `tagmemorag_tag_pyramid_residual_prior_applied_total{kb_name}` increments once per `ResidualPyramid.analyze` call when prior weighting is active.

## Rollout / Rollback

- Safe rollout: producer writes table by default, but consumers remain disabled until `intrinsic_residuals_enabled=true`.
- Rollback: turn the flag off. Existing table rows can remain; they are ignored by online code.
