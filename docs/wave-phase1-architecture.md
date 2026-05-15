# Wave Phase 1: Co-occurrence Matrix + V6 Spike Propagation

> Status: shipped behind `wave_phase1.spike_enabled` (default **false**).
> Source algorithm reference: VCPToolBox `TagMemoEngine.applyTagBoost` /
> `buildDirectedCooccurrenceMatrix`.

## What Phase 1 does

Phase 0 wrote tag data into SQLite (`tags` / `manual_tags(position)` /
`tag_intrinsic_residuals`) but search did not consume any of it. Phase 1 is
the first time the search path reads tag data.

It adds **two artefacts** to the system:

1. **Per-KB directed co-occurrence matrix** — `data/_global/tag_cooccurrence/{kb}.npz`,
   built at the end of every rebuild from `manual_tags(position)` rows.
2. **Query-vector enhancement** — when `wave_phase1.spike_enabled=true`, an LIF
   spike walk over the matrix produces a "tag context vector" that is fused into
   the query vector before vector search runs.

Both pieces are implemented as additive layers; flipping `spike_enabled=false`
returns the search path to Phase 0 byte-for-byte.

## Module layout

| Module | Purpose |
| --- | --- |
| `src/tagmemorag/tag_cooccurrence.py` | `CooccurrenceMatrix` dataclass, `build_cooccurrence_for_kb`, atomic save/load |
| `src/tagmemorag/wave_tag_spike.py` | `propagate()` (V6 spike) + `apply_tag_boost()` (5-step pipeline) |
| `src/tagmemorag/tag_rebuild.py` | Hooks `_rebuild_cooccurrence` after EPA retrain |
| `src/tagmemorag/search_runtime.py` | Calls `apply_tag_boost` before `wave_search`, propagates `tag_boost_info` to debug |
| `src/tagmemorag/wave_searcher.py` | Accepts `disable_legacy_tag_boost` to silence chunk-side `tag_boost` while spike is on |

## Data layout

```
data/
└── _global/
    ├── epa_basis.npz              # Phase 0
    └── tag_cooccurrence/
        └── {kb_name}.npz          # Phase 1 — per-KB
```

NPZ schema (version 1):

```
source_ids: int64[E]   # source tag id (earlier-position tag)
target_ids: int64[E]   # target tag id (later-position tag)
weights:    float32[E] # accumulated phi-pair weight
meta_kb_name:        object scalar
meta_built_at:       object scalar (ISO timestamp)
meta_schema_version: int32 scalar
```

Edges are sorted by `(source_id, target_id)` so two builds over the same data
produce byte-identical files modulo `meta_built_at`. Atomic write follows the
same `tmp → fsync → replace → fsync(dir)` pattern as `epa_basis.save_epa_basis`.

## Algorithm summary

### Builder

For each manual with `n` tags ordered by position:

```
phi(pos, n) = phi_max - (phi_max - phi_min) * (pos - 1) / (n - 1)
edge_weight(t_i → t_j) += phi(pos_i) * phi(pos_j)   # i < j
```

- `phi_max=0.9, phi_min=0.5` (source PHI_MAX/PHI_MIN).
- Direction: earlier-position tag is **source**, later-position is **target**.
- Per-manual guard: `n<2` or `n>max_tags_per_manual` (default 100) ⇒ skip.
- Legacy fallback: rows with `position=0` produce symmetric edges with
  weight `cnt * legacy_phi^2` (`legacy_phi=0.7`).

### Spike propagation (V6)

The seed set comes from top-K cosine over canonical tag vectors (Phase 1
substitute for `ResidualPyramid`). Each seed fires with `seed_similarity` energy
and `base_momentum=2.0` TTL. On each hop, every active spike injects current
into its top-K neighbours:

```
tension = cooc_weight * residual          # residual = 1.0 by default
is_wormhole = tension >= tension_threshold (1.0)
decay = wormhole_decay (0.70) if wormhole else base_decay (0.25)
momentum_cost = 0 if wormhole else 1
injected = energy * cooc_weight * decay   # skip if < 0.01
```

Stopping conditions: `max_hops=4`, `firing_threshold=0.10` on remaining energy,
`max_neighbors_per_node=20`, `max_emergent_nodes=50`. All defaults are sourced
from VCPToolBox `srConfig` and exposed under `wave_phase1.spike_*`.

### Boost integration

`apply_tag_boost(query_vec, kb_name, settings, base_tag_boost)` runs:

1. Seed selection — top-K cosine from `iter_canonical_tags_with_vectors`.
2. Spike propagation through the cooccurrence matrix.
3. Merge seeds + emergent (cap at `max_emergent_nodes`).
4. Semantic dedup (cosine > 0.88 ⇒ merge weight with 20% transfer).
5. Build context vector (weighted mean → L2 normalize).
6. Fuse: `query' = (1-α)·query + α·context`, `α = min(1, base_tag_boost * dynamic_factor)`.

The `dynamic_boost_factor_strategy` knob picks how `dynamic_factor` is computed:
- `"constant"` (default) — `1.0`. Visible boost while EPA is cold-start.
- `"epa"` — `max(epa_floor, logicDepth * epa_logic_depth_scale)`, where
  `logicDepth` comes from `epa_projector.project(query)`. Falls back to
  constant if the basis cannot be loaded.

### EPA dynamic boost: cold-start vs real-PCA

Keep `dynamic_boost_factor_strategy: constant` until the global EPA basis has
graduated to `train_kind="real-pca"`. With the default production
`wave_phase0.epa_min_k=8`, that requires at least 16 canonical tags across the
registry. Below that threshold EPA writes an identity cold-start basis; this is
safe, but the resulting logicDepth is a bootstrap signal rather than a trained
PCA signal.

Before switching a deployment to `dynamic_boost_factor_strategy: epa`, run:

```bash
uv run python scripts/diag_epa_logic_depth.py
```

The diagnostic prints cold-start and real-PCA logicDepth/alpha distributions
and the PCA explained-variance ratio. The Phase 2a fixture needs
`epa_logic_depth_scale: 2.0` to make real-PCA alpha variation clear under the
hashing embedder; `epa_floor` stays `0.0`, so degenerate projections still fall
through to `dynamic_boost_min`. If EPA tuning regresses quality, switch back to
`constant`; Phase 2b will add ResidualPyramid features to complete the broader
dynamicBoostFactor formula.

Failures degrade silently: missing matrix, no seeds, degenerate context vector,
or zero α each return the original query plus a `TagBoostInfo` with
`skipped_reason` populated.

## Configuration

```yaml
wave_phase1:
  enabled: true                # master switch (also gates the rebuild step)
  spike_enabled: false         # query-vector enhancement on/off — default OFF
  cooccurrence_enabled: true   # rebuild step on/off

  phi_max: 0.9
  phi_min: 0.5
  legacy_phi: 0.7
  max_tags_per_manual: 100

  spike_max_hops: 4
  spike_base_momentum: 2.0
  spike_firing_threshold: 0.10
  spike_base_decay: 0.25
  spike_wormhole_decay: 0.70
  spike_tension_threshold: 1.0
  spike_max_emergent_nodes: 50
  spike_max_neighbors_per_node: 20

  seed_top_k: 8
  seed_min_similarity: 0.3

  dynamic_boost_factor_strategy: constant   # "constant" | "epa"
  dynamic_boost_min: 0.3
  dynamic_boost_max: 2.0
  epa_logic_depth_scale: 2.0
  epa_floor: 0.0

  dedup_threshold: 0.88
  dedup_weight_transfer: 0.2

  legacy_chunk_tag_boost: false   # escape hatch: keep chunk-side bonus when spike is on
```

## Kill switches and rollback

Soft rollback (preserve data, restore behaviour):

```yaml
wave_phase1:
  spike_enabled: false
```

This puts the search path back to Phase 0 with no observable difference.

Hard rollback (also remove generated data):

```bash
rm -rf data/_global/tag_cooccurrence/
```

The loader returns `None` on missing files, so deletion is safe — the next
search short-circuits to the original query vector.

If spike-on shows quality regressions, flip the escape hatch instead of
turning the spike off entirely:

```yaml
wave_phase1:
  spike_enabled: true
  legacy_chunk_tag_boost: true   # keep chunk-side tag bonus alongside spike
```

This re-enables the chunk-side `metadata_field_boost` for the `tags` field,
giving you a halfway state for diagnosis.

## Observability

Three new Prometheus series (low cardinality — kb_name + outcome only):

| Metric | Type | Description |
| --- | --- | --- |
| `tagmemorag_tag_cooccurrence_edges{kb_name}` | Gauge | Directed edge count after the latest rebuild |
| `tagmemorag_tag_cooccurrence_rebuild_duration_seconds{kb_name, outcome}` | Histogram | Duration; outcome ∈ {success, failed} |
| `tagmemorag_tag_spike_propagations_total{kb_name, outcome}` | Counter | Per-query spike outcome ∈ {applied, skipped} |

Per-query telemetry that needs higher cardinality (skipped reason, seed count,
matched tag names) lives on `SearchExecution.tag_boost_info` and the API debug
payload (`debug.tag_boost`), not on metric labels.

## Compatibility

- Phase 0 e2e baseline invariance still passes when `spike_enabled=false`.
- `search.tag_boost = 0.03` keeps its numeric value. When spike is on, it
  is consumed as `base_tag_boost` in the query-vector blend; the chunk-side
  bonus inside `wave_searcher` is silenced unless `legacy_chunk_tag_boost=true`.
- An old `config.yaml` without a `wave_phase1` section gets defaults equivalent
  to "off" — no behaviour change.
- Removing `data/_global/tag_cooccurrence/` does not crash search.

## Tuning notes

- `seed_min_similarity` is the most useful first knob. Hashing dim=64 produces
  noisier cosines than SiliconFlow dim=384 — start at 0.3, raise toward 0.5
  if seed selection drifts off-topic.
- `dedup_threshold=0.88` matches the source. If hashing baselines diverge
  significantly from siliconflow on `precision_at_k`, this is a likely cause.
- `spike_max_hops=4` is conservative. Increasing it without raising
  `firing_threshold` can let weak signals dominate.

## Future extension points

- **Phase 2b**: replace the top-K cosine seed selector with `ResidualPyramid`
  Gram-Schmidt energy decomposition.
- **Phase 3**: train real `tag_intrinsic_residuals` so the wormhole gate
  becomes meaningful (currently `residual=1.0` ⇒ wormhole iff `cooc_weight≥1.0`).
- **Phase 4**: V8 `geodesicRerank` will read `lastEnergyField` from the spike
  result (already cached in memory but not exposed yet).
