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

- **Phase 2b-2**: worldview gating + language penalty + ghost tag injection
  (V6 source `[4]` modulators); requires Phase 2b-1's pyramid `levels` and
  EPA real-PCA `dominantAxes[0].label`.
- **Phase 3**: train real `tag_intrinsic_residuals` so the wormhole gate
  becomes meaningful (currently `residual=1.0` ⇒ wormhole iff `cooc_weight≥1.0`).
- **Phase 4**: V8 `geodesicRerank` will read `lastEnergyField` from the spike
  result (already cached in memory but not exposed yet).

## ResidualPyramid: multi-level Gram-Schmidt (Phase 2b-1)

Phase 2b-1 ports `Plugin/TagMemo/ResidualPyramid.js` (V3.7) and replaces the
top-K cosine seed selector with multi-level energy decomposition. New module
`src/tagmemorag/residual_pyramid.py` exposes
`ResidualPyramid(tag_rows, ...).analyze(query_vec) -> PyramidResult`.

`analyze` iterates up to `pyramid_max_levels` (default 3) layers:

1. Top-K cosine recall against the **current residual** (not the original
   query) — re-uses the in-memory `tag_rows` matrix loaded by `apply_tag_boost`.
2. Modified Gram-Schmidt: orthonormalize the K tag vectors and project the
   current residual; record `basis_coefficients[i] = |<query, u_i>|` as each
   tag's `contribution`. Linearly-dependent tags get coefficient 0.
3. Energy bookkeeping: `energy_explained_by_level = (||R_old||² - ||R_new||²) / originalEnergy`.
4. **Level-0 only** (port depth L2, see PRD D2): handshake submodule computes
   `direction_coherence` (mean-direction magnitude of `query - tag_i` deltas)
   and `pattern_strength` (pairwise direction sim over the first 5 candidates).
5. Stop when `||R||² / originalEnergy < pyramid_min_energy_ratio` (default 0.1)
   or when `max_levels` is reached.

The derived `features` dict drives the dynamic boost formula:

```
coverage             = min(1, total_explained_energy)
coherence            = level0.handshake.pattern_strength
noise_signal         = (1 - direction_coherence) * (1 - pattern_strength)
tag_memo_activation  = coverage * coherence * (1 - noise_signal)
```

### dynamicBoostFactor strategy comparison

| Strategy | Formula | When to use | Default? |
|---|---|---|---|
| `constant` | `dynamic = 1.0` | Phase 1 baseline; no EPA training; spike-off invariance | ✅ default |
| `epa` | `max(epa_floor, logicDepth * epa_logic_depth_scale)` | EPA real-PCA available; want a single-knob lever | opt-in |
| `pyramid` | `(logicDepth * (1+log(1+resonance)) / (1+entropy*0.5)) * activation_mult * pyramid_post_scale`, floored at `epa_floor` | EPA real-PCA available; want full source formula with feature-driven boost | opt-in |

`resonance` is stubbed at 0 (Phase 0/1/2a/2b-1 do not implement
`detectCrossDomainResonance`); `log(1 + 0) = 0` ⇒ that term degenerates to 1.0.

`pyramid_post_scale = 4.0` is calibrated against the hashing dim=64 / 12-tag
fixture so the alpha series passes D2 thresholds (`std > 0.005` and
`range/mean > 0.1`). It is **decoupled** from `epa_logic_depth_scale = 2.0`
because the two formulas have very different magnitudes:
- `epa`: `max(floor, logicDepth * 2.0)` — directly amplifies logicDepth
- `pyramid`: full formula × `tag_memo_activation`-driven activation (mean ~0.17
  on the fixture) × post-scale; the activation factor compresses output, so a
  larger post-scale is needed to hit the same alpha magnitude as `epa`.

### Failure / degradation paths

- `originalEnergy < 1e-12` (zero query) ⇒ empty result with `tag_memo_activation = 0`.
- `tagIndex.search` empty / GS all linearly dependent ⇒ no candidates this
  level; iteration stops; partial pyramid still returned.
- ResidualPyramid raises on `apply_tag_boost`'s strategy="pyramid" path ⇒
  caller falls back to the cosine `_select_seeds` path and passes
  `pyramid_features=None` to `_resolve_dynamic_boost` (which yields
  `tag_memo_activation = 0` ⇒ `act_mult = act_min`).
- `pyramid_use_handshake_features=false` ⇒ no handshake on level-0 ⇒
  `coherence = 0` ⇒ `tag_memo_activation = 0` (degenerate L1 mode without
  removing the module).

### Performance budget

`max_levels=3 × top_k=10 × O(dim²)` Gram-Schmidt + cosine. At `dim=384` this is
~4.4M FMA per query (< 5 ms in NumPy). Each pyramid call observes 4 metrics:
`tag_pyramid_levels`, `tag_pyramid_explained_energy`, and three
`tag_pyramid_features` gauges (`tag_memo_activation` / `coverage` /
`coherence`). `tag_dynamic_factor` is observed for every spike-on call across
all strategies for dashboard visibility.

### Diagnostic & rollback

- Validate before switching: `uv run python scripts/diag_pyramid_dynamic_boost.py`
  must report `overall: PASS`. Output also includes the `constant` and `epa`
  paths for side-by-side comparison.
- Soft rollback (config-only): set `dynamic_boost_factor_strategy: epa` (back to
  Phase 2a) or `constant` (back to Phase 1).
- Mid-rollback (keep pyramid, kill features): set
  `pyramid_use_handshake_features: false`.

## External modulators (Phase 2b-2)

Phase 2b-2 adds the V6 `applyTagBoost`'s 4 peripheral modulators on top of the
ResidualPyramid candidate-collection step. They are wired in at two anchors of
the search runtime, both gated by `strategy="pyramid"`:

```
Phase 2b-1 path (unchanged):
  pyramid → spike merge → semantic dedup → context vector → fused output

Phase 2b-2 inserts modulators at marked anchors:
  pyramid candidates                                  ┐
    weight ← contribution × layer_decay               ├ ★ langPenalty + coreBoost
              × langPenalty(tag, queryWorld)          │   here, per-candidate
              × coreBoost(is_core, sim, dynamicCore)  ┘

  spike merge (seeds + emergent)
    ★ core completion: SQL-pull caller's core_tags missed by pyramid
    ★ ghost injection: caller-supplied vectors with negative ids

  → (existing) dedup + context vector + fused output
```

### Inputs

`apply_tag_boost(..., core_tags=Sequence[str], ghost_tags=Sequence[GhostTag])`:

- **`core_tags`**: arbitrary strings; resolved via `tag_governance.resolve_tag`
  (synonym → canonical, lowercase, dedup). Recorded in
  `TagBoostInfo.core_tags_input` (post-clean) and `core_tags_resolved`
  (post-resolve). Unknown tags pass through; the SQL completion lookup may still
  hit them if KB has the exact name.
- **`ghost_tags`**: list of `GhostTag(name, vector: np.ndarray, is_core: bool)`.
  `vector.shape` must equal `(model.dim,)`; mismatches are silently skipped and
  counted in `info.ghost_skipped_dim_mismatch`. Hard ghosts (`is_core=True`)
  get the `dynamicCoreBoostFactor` multiplier; soft ghosts use unit weight.

### langPenalty trigger matrix

| `query_world` (EPA dominant axis label) | Tag name shape | Triggered? | Multiplier |
| --- | --- | --- | --- |
| Empty / `Unknown` | Pure ASCII, len > 3, no CJK | ✅ | `lang_penalty_unknown` (0.4) |
| Matches `^[A-Za-z0-9\-_.]+$` (e.g. `axis-0`, `cooling`) | any | ❌ | 1.0 |
| Matches social regex (`Politics & Society`) | Pure ASCII, len > 3 | ✅ | `sqrt(lang_penalty_cross_domain)` |
| Otherwise (e.g. `Cooking & Recipes`) | Pure ASCII, len > 3 | ✅ | `lang_penalty_cross_domain` (0.3) |
| Any | Contains CJK or len ≤ 3 | ❌ | 1.0 |

The flag `wave_phase1.lang_penalty_enabled` (default `false`) gates the entire
matrix; with the default cold-start EPA basis emitting `axis-N` labels nothing
fires. The hashing-fixture eval suites therefore stay byte-stable even with
the flag on.

### dynamicCoreBoostFactor formula

```
coreMetric = 0.5 × clamp(logicDepth) + 0.5 × (1 − clamp(coverage))
factor     = core_boost_min + clamp(coreMetric, 0, 1) × (core_boost_max − core_boost_min)
```

Defaults `[1.20, 1.40]` track V6 source. EPA failure ⇒ `logicDepth = 0` ⇒ factor
sits at `core_boost_min` (conservative). `coverage` comes from
`PyramidFeatures.coverage`; absent on non-pyramid strategies (so the formula
collapses to its midpoint and only hits ghost / completion paths under
`strategy="pyramid"`).

### Ghost id convention & dim check

- Ghost ids decrement from `-1` and never reuse, so they cannot collide with KB
  tag ids (which are positive) or each other.
- Vector dim is checked against `query_vec.shape[0]`; mismatched ghost is
  skipped + counted (no exception). Empty `name` is treated as a dim-mismatch.
- After injection, ghosts flow through the same dedup / context / fuse path as
  real candidates — caller does not need to special-case them.

### Observability (3 new metrics)

| Name | Type | Labels | Buckets |
| --- | --- | --- | --- |
| `tagmemorag_tag_lang_penalty_applied` | Counter | `kb_name, query_world_kind ∈ {unknown, social, cross_domain_other, technical, disabled}` | — |
| `tagmemorag_tag_core_tags_resolved` | Histogram | `kb_name` | `(0,1,2,3,5,8,13)` |
| `tagmemorag_tag_ghosts_injected` | Histogram | `kb_name, kind ∈ {hard, soft, skipped_dim}` | `(0,1,2,3,5,8,13)` |

`record_tag_lang_penalty_applied` only fires when the multiplier is `< 1.0`
(actually applied); `record_tag_core_tags_resolved` reports the post-resolve
`canonical` count regardless of strategy.

### Phase 3 follow-ups

- Replace `resonance = 0` stub with real `detectCrossDomainResonance` (uses
  EPA basis cross-axis mass). **Implemented** — see "Cross-domain resonance"
  below; default off pending production rollout.
- Add explicit `worldview gating` if real-deployment data shows a single
  langPenalty multiplier is too coarse (currently V6 only uses `queryWorld`
  to gate langPenalty, not as an independent projection filter).
- Re-baseline `siliconflow.json` once production EPA labels stabilize and
  langPenalty starts firing in real fixtures.

## Cross-domain resonance (Phase 3)

Phase 3 ports V6 `EPAModule.detectCrossDomainResonance` (source:
`lioensky/VCPToolBox` `EPAModule.js:170-201`, commit `aff66193`) into
`wave_tag_spike.detect_cross_domain_resonance`. The helper consumes the
EPA `dominantAxes` already produced by `EPAProjector.project()` and returns
`(resonance, bridges)`:

```
for sec in dominantAxes[1:]:
    co_act = sqrt(top.energy * sec.energy)
    if co_act > 0.15:
        bridges.append({from: top.label, to: sec.label,
                        strength: co_act,
                        balance: min/max(top.energy, sec.energy)})
resonance = sum(bridge.strength)
```

The threshold `0.15` is hardcoded — V6 does not expose it via config and we
mirror that decision (PRD D6). The wiring point is the existing pyramid
branch of `_resolve_dynamic_boost_with_world`:

```
resonance = 0.0
if cfg.cross_domain_resonance_enabled:
    resonance, bridges = detect_cross_domain_resonance(dominant)
resonance_term = log(1 + max(0, resonance))
dynamic = (logic_depth * (1 + resonance_term) / (1 + entropy * 0.5))
        * activation_mult
```

**Data contract additions:**

- `WavePhase1Config.cross_domain_resonance_enabled: bool = False`.
- `TagBoostInfo.cross_domain_resonance: float`,
  `cross_domain_bridges_count: int` (in `to_dict`).
- Private `TagBoostInfo._cross_domain_bridges: tuple[dict, ...]` (excluded
  from `to_dict`; surfaced under
  `search_debug_payload.tag_boost_debug.cross_domain_bridges` only when at
  least one bridge survived the threshold).

**Observability:** two histograms gated by the config flag —

- `tagmemorag_tag_resonance_value{kb_name}`: scalar fed to the log term, with
  buckets `(0, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2, 2.0, 4.0)` covering the PRD
  log-domain table.
- `tagmemorag_tag_resonance_bridges_count{kb_name}`: number of bridges per
  call, buckets `(0, 1, 2, 3, 5, 8)`. Bridge labels are deliberately *not*
  exposed as Prometheus labels (high cardinality).

**Default off rationale:** 8 hashing eval suites are anchored to the
Phase 2b-2 baseline; `cross_domain_resonance_enabled=false` keeps the
formula numerically equivalent to Phase 2b-1, so flipping the toggle is a
pure runtime choice. The `pyramid+resonance` column in
`scripts/diag_pyramid_dynamic_boost.py` PASSes the D2 thresholds at the
default `pyramid_post_scale=4.0`, so no recalibration was applied at
implementation time.

**Future work:** Phase 3.5 trains real `tag_intrinsic_residuals` and feeds
them into the ResidualPyramid as a prior; Phase 4 covers V8
`geodesicRerank`.

## Geodesic rerank (Phase 4)

Phase 4 ports VCPToolBox V8 `TagMemoEngine.geodesicRerank`
(`TagMemoEngine.js:537-640`). After Phase 1 spike propagation has produced
a tag-energy field (`SpikeResult.accumulated_energy`), V8 reranks the
KNN+wave candidates by mean tag energy per chunk, blending with the
original score:

```
geo_score      = sum(energy_field[tid] for tid in chunk.tags) / hit_count
normalized_geo = geo_score / max_geo                  # [0, 1] across pool
final_score    = (1 - α) * knn_score + α * normalized_geo
```

Three-layer fallback (matches source-side defense):

| Layer | Trigger | Behavior |
|-------|---------|----------|
| L0 | `energy_field` is empty / None | Return input candidates verbatim, reason `energy_field_empty` |
| L1 | per-candidate hit count < `min_geo_samples` | That candidate's `geo_score = 0` |
| L2 | global `max_geo == 0` | Return input order verbatim, reason `max_geo_zero` |

### Configuration

| Setting | Default | Note |
|---------|---------|------|
| `wave_phase1.geodesic_rerank_enabled` | `false` | Single consumer flag; honors Phase 2b-2 / 3 / 3.5 default-off pattern |
| `wave_phase1.geodesic_alpha` | `0.3` | Blend weight; clamped to `[0, 1]` |
| `wave_phase1.geodesic_oversample_factor` | `2.0` | `pool = top_k × factor`; lower bound 1.0 |
| `wave_phase1.geodesic_min_geo_samples` | `2` | **Differs from source default 4** because this repo's manuals carry ~3 tags/chunk on average; raise to 4 once tag density is ≥6/chunk |

### Hard dependency on Phase 1 spike

V8 only runs when `wave_phase1.spike_enabled=true` AND
`geodesic_rerank_enabled=true` AND `apply_tag_boost` succeeded with a
non-empty `accumulated_energy`. If the flag is on but any precondition
fails, V8 silently no-ops and records `geodesic_rerank_skipped_total{reason}`
with a fixed-cardinality reason from this whitelist:

```
spike_disabled       — kill switch off
matrix_missing       — cooccurrence matrix not on disk yet
no_tag_vectors       — KB tags exist but no vectors loaded
no_seeds             — pyramid / cosine seed selection produced empty set
no_candidates        — spike + dedup left no candidates to fuse
degenerate_context   — fused context vector was zero
zero_alpha           — base_tag_boost × dynamic clamped to 0
degenerate_fused     — boosted vector had near-zero norm
energy_field_empty   — spike ran but produced no energy entries
max_geo_zero         — V8 ran, every candidate's geo_score was 0 (L2)
lexical_only_path    — execute_search fell back before spike (no boost_info)
unknown              — catchall (should not happen if config is valid)
```

### Observability

Four metrics, all gated to record only when `geodesic_rerank_enabled=true`:

- `tagmemorag_geodesic_rerank_applied_total{kb_name}` — Counter, V8 actually
  contributed a reranking (`applied=True`).
- `tagmemorag_geodesic_rerank_skipped_total{kb_name, reason}` — Counter.
  `reason` is bounded to the whitelist above.
- `tagmemorag_geodesic_rerank_swap_total{kb_name, kind}` — Counter,
  `kind ∈ {rank_changed, new_entry, lost_entry}`. Per-query swap
  classification against the input top_k.
- `tagmemorag_geodesic_rerank_hit_count_observed{kb_name}` — Histogram,
  per-candidate tag hit count, buckets `(0, 1, 2, 3, 4, 6, 10)`.

### Default off rationale

8 hashing eval suites are anchored to baseline (Phase 2b-2 + 3 + 3.5
behavior). `geodesic_rerank_enabled=false` keeps `wave_search` byte-equivalent
to the previous shape (no oversampling, no rerank, no metric registration).
With the flag on at default α=0.3 / min_samples=2, `scripts/run_eval_ci.py
--geodesic` reports informational deltas; the column does NOT gate CI —
recovery is the responsibility of a separate readiness task.
`scripts/diag_geodesic_rerank.py` on the product-manual fixture set hits
`applied_pct=100% / max_geo_zero=0%`, confirming V8 has real signal in this
repo.

## Eval baselines (hashing vs siliconflow)

Two baseline files live under `tests/fixtures/eval/baselines/`:

| File | Embedder | Role | CI consumed by default? |
|------|----------|------|--------------------------|
| `hashing.json` | hashing 64-dim | Quality gate — `run_eval_ci.py` default | Yes (always) |
| `siliconflow.json` | Qwen3-VL-Embedding-8B 4096-dim | Informational reference for readiness work | No |

`hashing.json` is the byte-stable PR gate (offline, fast, deterministic). It
is what every commit on this branch exercises through GitHub Actions.

`siliconflow.json` captures the production embedder's measurements over the
same 8 fixture suites. It is **not** a quality gate today because:

1. Fixture eval suites' case-level thresholds (`min_hit_at_k`, `min_mrr`, etc.)
   were authored against hashing-embedder-recall; the same chunks won't
   necessarily be top-K under a real semantic embedder.
2. Several wave_phase1 parameters (`spike_firing_threshold`, etc.) are tuned
   on hashing dim=64; magnitudes shift at 4096 dim.

Refresh siliconflow.json with `scripts/build_eval_baseline.py --embedder
siliconflow --compare-with tests/fixtures/eval/baselines/hashing.json` —
the script does an upfront single-query smoke test, runs each suite under
exponential-backoff retry (1s/2s/4s/8s/16s, hard errors like 401/403/404
short-circuit), writes atomically, and prints a per-suite per-metric delta
table to stdout. Diagnosing the gap and (eventually) reauthoring the
fixture suite to match the production embedder is the job of a separate
readiness task.
