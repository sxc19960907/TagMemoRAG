# Phase 1 Open Questions

> Things the source code is ambiguous about, or where multiple reasonable
> Python interpretations exist. Each item is something the implement.md author
> should make a deliberate call on.

## Algorithmic ambiguities

### Q1. EPA `dynamicBoostFactor` formula with cold-start basis

The source formula (TagMemoEngine.js:88):
```
dynamicBoostFactor = (logicDepth * (1 + log(1+resonance)) / (1 + entropy*0.5)) * activationMultiplier
```

With Phase 0 cold-start basis (identity[:K]):
- `logicDepth = 1 - normalizedEntropy`. For a query that has roughly equal projection onto all K identity rows, `normalizedEntropy ≈ 1`, so `logicDepth ≈ 0`.
- `resonance = 0` (no `detectCrossDomainResonance` in Phase 1).
- `entropy ≈ 1` for the same reason.
- Without ResidualPyramid, `activationMultiplier` defaults to a constant.

Net: `dynamicBoostFactor ≈ 0 * 1 / 1.5 * const = 0`, then clamped up to `0.3` by `boostRange`. So `effectiveTagBoost = baseTagBoost * 0.3 = 0.009` (with default `baseTagBoost=0.03`). Very small.

**Question**: Should Phase 1 force `dynamicBoostFactor = 1.0` (skip the EPA term entirely until EPA is trained) so the tag boost has visible effect, or keep the formula and accept that the boost is small until later phases?

Two reasonable answers:
- (a) Keep formula, ship with small boost. Pro: matches source; later EPA training "turns it on" without code change. Con: AC tests for boost effect are hard to write because the effect is tiny.
- (b) Add `wave_phase1.dynamic_boost_factor_strategy: "epa" | "constant"` with default `constant`, value `1.0`. Switch to `"epa"` when EPA is trained. Pro: more visible spike in Phase 1; deterministic for tests. Con: deviates from source.

**Recommendation**: (b). Phase 0 explicitly noted EPA cold-start is "best-effort placeholder"; treating it as such in Phase 1 is consistent. Document the switch.

### Q2. `LEGACY_PHI` fallback path — keep or skip?

Source step 3 (TagMemoEngine.js:707-728) handles the case where some `file_tags.position = 0`. TagMemoRAG Phase 0 always writes 1-indexed positions, so on a fresh build the legacy branch is dead code.

**However**:
- Bulk-imported manuals from Phase 0 pre-write may exist if a deployment ran the schema migration before Phase 0 incremental_rebuild touched all manuals.
- If a future bug writes `position=0`, the legacy path gracefully degrades.

**Recommendation**: Port it. Cost is ~30 lines and one extra SQL query during rebuild. Adds resilience.

### Q3. Direction interpretation when n=2

For `n=2`, `phi(pos=1, n=2) = 0.9`, `phi(pos=2, n=2) = 0.5`. So a 2-tag manual contributes `0.9 * 0.5 = 0.45` to the directed edge `tags[0] → tags[1]`. The reverse edge gets nothing.

**Question**: Is the asymmetry desired for n=2? The spec specifies "specific to broad" tag ordering, so yes — `[fault-code, washer]` should activate "washer" more strongly than "fault-code → washer" should activate the reverse.

**Recommendation**: Match source exactly. No special-casing.

### Q4. Spike propagation direction

The spike traverses outgoing edges only (`tagCooccurrenceMatrix.get(nodeId)` returns targets where nodeId is the source). Combined with "early position = source", spikes flow **specific → broad**.

**Question**: Should spikes also flow the other way (broad → specific)?

The source explicitly does not. The reasoning is in the docstring intent: a specific seed tag activates broader categories that then participate in chunk scoring. Reverse traversal would activate more specific tags from a broad seed, diluting the signal.

**Recommendation**: Match source exactly — outgoing only.

### Q5. Wormhole gate with residuals all = 1.0

V7's wormhole: `tension = coocWeight * residual`, `isWormhole = tension >= TENSION_THRESHOLD (1.0)`.

In Phase 1, all residuals = 1.0 (Phase 0 D3 default). So `isWormhole ⇔ coocWeight ≥ 1.0`.

This means edges with high accumulated co-occurrence weight (≥ 1.0) get the wormhole bonus: 0.70 decay instead of 0.25 decay, 0 momentum cost instead of 1.

**Is this meaningful in Phase 1?** Yes:
- A pair of tags that co-occurs in many manuals will accumulate weight > 1.0. Phi-pair max = 0.81 per file; 2 manuals at peak = 1.62.
- Effectively the wormhole gate becomes "is this a frequently co-occurring strong-position pair?" — a reasonable signal even without true V7 residuals.

**Recommendation**: Keep the wormhole logic. Port it. Document that `tagIntrinsicResiduals` will activate it more discriminatingly when Phase 3 lands.

### Q6. Neighbour cap with small fixtures

`MAX_NEIGHBORS_PER_NODE = 20`. With Phase 0 fixture (4 KBs, 12 canonical tags), no node will ever have ≥20 neighbors. The cap is dead code in test fixtures.

**Question**: Default to 20 (match source) or smaller (e.g. 10) to make the cap testable on fixture data?

**Recommendation**: Match source default (20). Add a unit test that builds a synthetic fixture with 30+ cooccurrences to exercise the cap explicitly.

### Q7. `MAX_EMERGENT_NODES = 50` cap

Same shape as Q6 — cap won't trigger on fixture-scale matrices.

**Recommendation**: Match source default. Add unit test with synthetic fixture.

### Q8. Per-KB matrix vs global matrix

Source has no kb_name. Python port options:
- (a) Per-KB matrix files. Spike inside one KB.
- (b) Global matrix across all KBs. Spike can cross KBs.

(b) sounds powerful but:
- Cross-KB tag activation has no precedent in the source.
- Search is per-KB; cross-KB candidates can't even be ranked together.
- The Phase 0 EPA basis is global, but only because PCA needs N≥K*2 samples and per-KB can't provide that. Co-occurrence has no such floor.

**Recommendation**: (a) per-KB. Maintains the existing per-KB isolation invariant.

### Q9. Semantic dedup threshold

Source: `cosine > 0.88` ⇒ merge weights with 20% transfer. Threshold is hard-coded in source but `config.deduplicationThreshold` overrides.

For TagMemoRAG hashing dim=64, cosine similarities are noisier. Some near-orthogonal tag pairs may exceed 0.88 by chance.

**Question**: Should Phase 1 default the threshold higher (0.92?) for the hashing embedder, or trust 0.88?

**Recommendation**: Keep 0.88 default (matches source). Add a note in the eval-baseline-workflow.md: if the hashing baseline diverges significantly from siliconflow on `precision_at_k`, dedup threshold is a likely cause.

## Edge cases the source handles (must be preserved)

| Case | Source behaviour | Phase 1 must do |
|---|---|---|
| `tagCooccurrenceMatrix === undefined` | Skip [4.5] entirely (line 186) | Same — no-op when matrix file missing |
| `allTags.length === 0` after collection | Skip [4.5]; `applyTagBoost` returns `{vector: original, info: null}` (line 374) | Same |
| `injectedCurrent < 0.01` | Skip neighbor (line 236) | Same constant |
| `nextMomentum < 0 && !isWormhole` | Skip (line 239) | Same |
| `propagated === false` after a hop | Break loop early (line 259) | Same |
| `originalEnergy < 1e-12` (residual pyramid) | Return empty result | N/A (no pyramid in Phase 1) |
| `totalWeight === 0` after weighted-mean | Return original vector unchanged (line 452) | Same — guards against degenerate boost |

## Performance pitfalls

### P1. `lru_cache` on cooccurrence matrix loader

Loading the npz on every search is slow. The cache key must include both `kb_name` and a freshness signal (file mtime). Don't pickle the cache key with default `id`-based hashing; ensure it's by value.

### P2. Spike inner loop

Pure-Python double loop over `(activeSpikes, neighbors)` could be slow on large matrices. With ≤10⁴ tags this is fine; instrument duration with the new metric so we have data for whether to vectorise later.

### P3. Per-query EPA call

`epa_projector.project(query_vec)` is called inside `apply_tag_boost`. With cold-start basis the projection is trivial (matrix-vector product over K=8 axes); negligible. With trained PCA basis (Phase 2b+) it's still K=8, no concern.

### P4. Embedder consistency

The cooccurrence matrix is built from `manual_tags(kb_name, manual_id, tag_id, position)` — pure SQL, no embedder needed. The query-side `apply_tag_boost` does need tag vectors (for seed selection and context vector). Vectors come from `tags.vector` BLOB written at rebuild time. **Rebuild and search must use the same embedder configuration**, or seed cosines will be meaningless. Phase 0 already enforces this via `cfg.model.dim` checks; Phase 1 inherits.

## Parameters needing defaults (consolidated)

```yaml
wave_phase1:
  enabled: true
  spike_enabled: true
  cooccurrence_enabled: true

  # Co-occurrence matrix builder
  phi_max: 0.9          # source PHI_MAX
  phi_min: 0.5          # source PHI_MIN
  legacy_phi: 0.7       # source LEGACY_PHI (for position=0 fallback)
  max_tags_per_manual: 100  # source guard against dirty data

  # Spike propagation
  spike_max_hops: 4
  spike_base_momentum: 2.0
  spike_firing_threshold: 0.10
  spike_base_decay: 0.25
  spike_wormhole_decay: 0.70
  spike_tension_threshold: 1.0
  spike_max_emergent_nodes: 50
  spike_max_neighbors_per_node: 20

  # Seed selection (substitute for ResidualPyramid)
  seed_top_k: 8
  seed_min_similarity: 0.3

  # Boost factor strategy
  dynamic_boost_factor_strategy: "constant"  # "epa" | "constant"; constant=1.0
  dynamic_boost_min: 0.3
  dynamic_boost_max: 2.0
  core_boost_min: 1.20
  core_boost_max: 1.40

  # Semantic dedup
  dedup_threshold: 0.88
  dedup_weight_transfer: 0.2

  # Compatibility
  legacy_chunk_tag_boost: false  # disable wave_searcher's existing tag_boost when spike is on
```

## Suggested AC list draft

These are seeds for PRD's AC section, not the final list:

- AC-α: Co-occurrence matrix builder, given a fixture with known tag positions, produces edges with the documented phi-pair weights (snapshot-test).
- AC-β: Spike propagation, given a 3-node chain with known weights, produces the analytically expected `accumulatedEnergy` map after one hop (algorithm-locking unit test).
- AC-γ: Wormhole gate fires for edges with `coocWeight ≥ 1.0` and uses the alternate decay/momentum factors.
- AC-δ: `wave_phase1.spike_enabled = false` ⇒ `execute_search` output is byte-identical to current master (rollback path works).
- AC-ε: `wave_phase1.spike_enabled = true` ⇒ all 8 eval suites pass against the new hashing baseline (precision/recall/MRR/hit at -2% threshold).
- AC-ζ: Rebuild pipeline writes `data/_global/tag_cooccurrence/{kb}.npz` atomically; corrupt file at startup is logged + ignored without crashing search.
- AC-η: Two consecutive rebuilds with no tag changes write byte-identical npz (modulo `built_at`).
- AC-θ: Cooccurrence matrix loader respects mtime cache invalidation: search picks up new matrix after a rebuild without process restart.
- AC-ι: Wave-searcher's `tag_boost` chunk-side bonus is disabled when `spike_enabled=true` (no double counting); flipping `legacy_chunk_tag_boost=true` re-enables it as escape hatch.
