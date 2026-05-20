# Source: applyTagBoost + V6 Spike Propagation

> Verbatim breakdown of `TagMemoEngine.applyTagBoost` (TagMemoEngine.js:61-501).
> The function is 440 lines; this doc captures the V6/V7 algorithm's data flow,
> the spike propagation step, and where the boost lands in the final score.

## Public signature & docstring

```js
/**
 * 🌟 TagMemo 浪潮 + EPA + Residual Pyramid + Worldview Gating + LIF Spike Propagation (V6)
 */
applyTagBoost(vector, baseTagBoost, coreTags = [], coreBoostFactor = 1.33)
```

Returns `{vector: Float32Array, info: {coreTagsMatched, matchedTags, boostFactor, epa, pyramid}}`.

The function **rewrites the query vector**. It does not score chunks directly — the new query vector is then sent to the existing vector search. So tag boost in source is implemented as a **query-vector enhancement**, not as a re-ranking step on retrieval results.

## High-level flow (8 sub-steps)

```
[1] EPA project           → epaResult.{logicDepth, entropy, dominantAxes}
                          → resonance, queryWorld
[2] Residual pyramid      → pyramid.{levels, totalExplainedEnergy, features}
[3] Dynamic boost factors → effectiveTagBoost, dynamicCoreBoostFactor
[4] Collect candidate tags from pyramid levels (with langPenalty + coreBoost + layerDecay)
[4.5] V6 Spike propagation through tagCooccurrenceMatrix  ← the part Phase 1 ports
[4.6] Core tag completion (DB lookup for missing core tags)
[4.7] Ghost tag injection (caller-provided synonyms)
[5] Batch fetch tag vectors from DB
[5.5] Semantic deduplication (cosine > 0.88 → merge weights)
[6]   Build context vector = weighted mean of tag vectors, normalize
[6']  Final fuse: query' = (1-α)·query + α·contextVec, normalize
                  with α = min(1, effectiveTagBoost)
```

## [1] EPA inputs (lines 71-83)

```js
const epaResult = this.epa.project(originalFloat32);
// returns {projections, probabilities, entropy, logicDepth, dominantAxes}
const resonance = this.epa.detectCrossDomainResonance(originalFloat32);
// returns {resonance: float}
const queryWorld = epaResult.dominantAxes[0]?.label || 'Unknown';
```

`logicDepth = 1 - normalizedEntropy` (EPAModule.js:151). High = focused query; low = scattered query. Phase 1 doesn't have `detectCrossDomainResonance`, so port should default `resonance = 0`.

`queryWorld` is the human-readable label of the top EPA axis. Used for "world-view gating" — tags whose semantics belong to a different "world" get penalised. **Phase 0 EPA is identity-cold-start**, so axis labels are `axis-0..axis-7`; `queryWorld` becomes `axis-0` etc. The port should keep the gating code path but accept that it's mostly inert until EPA is properly trained.

## [2] Residual pyramid (lines 76-77)

```js
const pyramid = this.residualPyramid.analyze(originalFloat32);
const features = pyramid.features;
// pyramid: {levels: [...], totalExplainedEnergy, finalResidual, features}
```

The pyramid is what selects the *initial seed tags* for spike propagation. Each level pulls top-K tags from a tag index, computes Gram-Schmidt orthogonal projection, and explains a fraction of the query's energy. Tags carry `{id, name, similarity, contribution, handshakeMagnitude}`.

**Phase 1 has no ResidualPyramid implementation.** The port has two options:
- (a) Port the pyramid alongside the spike (Phase 2b territory; large scope).
- (b) Substitute a simple "top-K tag-vector cosine" as the seed selector and skip the multi-level energy decomposition.

Option (b) is much smaller and gives a working spike. The port can add the pyramid later without changing the spike algorithm. **Recommend (b) for Phase 1.**

## [3] Dynamic boost factors (lines 79-98)

```js
const actRange = config.activationMultiplier || [0.5, 1.5];
const activationMultiplier = actRange[0] + features.tagMemoActivation * (actRange[1] - actRange[0]);
const dynamicBoostFactor = (logicDepth * (1 + log(1+resonance)) / (1 + entropy*0.5)) * activationMultiplier;
const boostRange = config.dynamicBoostRange || [0.3, 2.0];
const effectiveTagBoost = baseTagBoost * clamp(dynamicBoostFactor, boostRange[0], boostRange[1]);

const coreMetric = (logicDepth * 0.5) + ((1 - features.coverage) * 0.5);
const coreRange = config.coreBoostRange || [1.20, 1.40];
const dynamicCoreBoostFactor = coreRange[0] + (coreMetric * (coreRange[1] - coreRange[0]));
```

`baseTagBoost` is the caller-supplied scalar (TagMemoRAG's existing `search.tag_boost = 0.03`). The dynamic factor multiplies/clamps it based on EPA + pyramid features. `pyramid.features.tagMemoActivation` and `pyramid.features.coverage` come from `ResidualPyramid._extractPyramidFeatures` — without the pyramid these don't exist. Phase 1 should treat them as constants (e.g. `tagMemoActivation = 0.5`, `coverage = 0.5`), making `dynamicBoostFactor = logicDepth` after simplification.

`effectiveTagBoost` is the **final α** for query-vector fusion in step [6'].

## [4] Tag candidate collection with three modulators (lines 132-182)

```js
levels.forEach(level => {
    tags.forEach(t => {
        // [a] Core boost (caller-marked tags get amplified)
        const coreBoost = isCore
            ? dynamicCoreBoostFactor * (0.95 + (t.similarity || 0.5) * 0.1)
            : 1.0;

        // [b] Language penalty (English tech tag in non-tech world → penalty)
        let langPenalty = 1.0;
        if (this.config.langConfidenceEnabled) {
            const isTechnicalNoise = !/[一-龥]/.test(t.name)
                                  && /^[A-Za-z0-9\-_.\s]+$/.test(t.name)
                                  && t.name.length > 3;
            const isTechnicalWorld = ...;
            if (isTechnicalNoise && !isTechnicalWorld) {
                const isSocialWorld = /Politics|Society|.../.test(queryWorld);
                const basePenalty = ...;
                langPenalty = isSocialWorld ? Math.sqrt(basePenalty) : basePenalty;
            }
        }

        // [c] Layer decay (deeper pyramid level → lower weight)
        const layerDecay = Math.pow(0.7, level.level);

        allTags.push({
            ...t,
            adjustedWeight: (t.contribution || t.weight || 0) * layerDecay * langPenalty * coreBoost,
            isCore,
        });
    });
});
```

Phase 1 port can simplify:
- Skip language penalty (TagMemoRAG fixture is English+Chinese mixed but no "world view" yet). Hard-set `langPenalty = 1.0`.
- Skip layer decay (no pyramid → no levels). Treat the simple cosine top-K as a single layer at level 0, `layerDecay = 1.0`.
- Keep core-tag boost. Caller can pass `coreTags` to highlight specific tags; if not, `coreBoost = 1.0`.

## [4.5] V6 Spike Propagation — the heart of Phase 1 (lines 186-309)

This is the section that consumes `tagCooccurrenceMatrix`. It runs **only if** `allTags.length > 0 && this.tagCooccurrenceMatrix`.

### Constants (lines 187-195)

```js
const MAX_SAFE_HOPS         = srConfig.maxSafeHops         ?? 4;
const BASE_MOMENTUM         = srConfig.baseMomentum        ?? 2.0;
const FIRING_THRESHOLD      = srConfig.firingThreshold     ?? 0.10;
const BASE_DECAY            = srConfig.baseDecay           ?? 0.25;
const WORMHOLE_DECAY        = srConfig.wormholeDecay       ?? 0.70;
const TENSION_THRESHOLD     = srConfig.tensionThreshold    ?? 1.0;
const MAX_EMERGENT_NODES    = srConfig.maxEmergentNodes    ?? 50;
const MAX_NEIGHBORS_PER_NODE = srConfig.maxNeighborsPerNode ?? 20;
```

These are the **default tunables**. Phase 1 should expose them in `wave_phase1` config block with the same defaults.

### Initial injection (lines 197-204)

```js
let activeSpikes = new Map();         // id → {energy, momentum}
const accumulatedEnergy = new Map();  // id → energySum (global)

allTags.forEach(t => {
    activeSpikes.set(t.id, { energy: t.adjustedWeight, momentum: BASE_MOMENTUM });
    accumulatedEnergy.set(t.id, t.adjustedWeight);
});
```

Each seed tag fires with its own `adjustedWeight` as initial energy and `BASE_MOMENTUM = 2.0` as TTL.

### Iteration loop (lines 207-263)

```js
for (let hop = 0; hop < MAX_SAFE_HOPS; hop++) {
    const nextSpikes = new Map();
    let propagated = false;

    for (const [nodeId, spike] of activeSpikes.entries()) {
        if (spike.energy < FIRING_THRESHOLD || spike.momentum < 0) continue;

        const synapses = this.tagCooccurrenceMatrix.get(nodeId);
        if (!synapses) continue;

        const sortedSynapses = Array.from(synapses.entries())
            .sort((a, b) => b[1] - a[1])
            .slice(0, MAX_NEIGHBORS_PER_NODE);

        for (const [neighborId, coocWeight] of sortedSynapses) {
            // V7 wormhole tension
            const neighborResidual = this.tagIntrinsicResiduals?.get(neighborId) ?? 1.0;
            const tension = coocWeight * neighborResidual;
            const isWormhole = tension >= TENSION_THRESHOLD;

            // Decay & momentum strategy
            const decayFactor   = isWormhole ? WORMHOLE_DECAY : BASE_DECAY;
            const momentumCost  = isWormhole ? 0 : 1.0;

            const injectedCurrent = spike.energy * coocWeight * decayFactor;
            if (injectedCurrent < 0.01) continue;

            const nextMomentum = spike.momentum - momentumCost;
            if (nextMomentum < 0 && !isWormhole) continue;

            // Aggregate at the receiving node
            const existing = nextSpikes.get(neighborId);
            if (existing) {
                existing.energy   += injectedCurrent;
                existing.momentum  = Math.max(existing.momentum, nextMomentum);
            } else {
                nextSpikes.set(neighborId, { energy: injectedCurrent, momentum: nextMomentum });
            }
        }
    }

    // Accumulate this hop into the global energy field
    for (const [nid, newSpike] of nextSpikes.entries()) {
        accumulatedEnergy.set(nid, (accumulatedEnergy.get(nid) || 0) + newSpike.energy);
        if (newSpike.energy > 0.01) propagated = true;
    }

    if (!propagated) break;
    activeSpikes = nextSpikes;
}
```

**Key observations**

1. The "wormhole" branch is a V7 feature using `tagIntrinsicResiduals`. Phase 1 has those residuals defaulting to `1.0` (Phase 0 schema decision D3). With `residual = 1.0`, `tension = coocWeight * 1.0 = coocWeight`. For tension ≥ 1.0, an edge with `coocWeight ≥ 1.0` is a wormhole.

   - In Phase 0 fixture: phi-pair weights stay below 1.0 (max is `0.81` from `0.9 * 0.9`), but multiple co-occurrences accumulate. With ~30 manuals sharing fault-code+washer the edge could exceed 1.0.
   - **Phase 1 default decision**: keep wormhole logic as-is. With residuals all 1.0 the wormhole gate becomes "is this a strong, repeatedly-co-occurring edge?" — that's a reasonable signal even pre-V7.

2. **Direction-asymmetric traversal.** The inner loop reads `tagCooccurrenceMatrix.get(nodeId)` — i.e. `nodeId` is treated as the *source*. A spike at node A only propagates along outgoing edges (A → ?), not incoming. With our convention (earlier-position tag is source), this means the spike flows from "specific" (early) tags to "broader" (late) tags. The `docs/tag-ordering-convention.md` specific-to-broad ordering is what makes this signal meaningful.

3. **Per-node neighbor cap** (`MAX_NEIGHBORS_PER_NODE = 20`) — a hub tag (e.g. `kitchen` co-occurring with everything) doesn't blow up the spike fan-out.

4. **Per-pulse minimum** (`injectedCurrent < 0.01` skip + `newSpike.energy > 0.01` propagation guard) — prevents pathological tail propagation.

### Aftermath (lines 266-309)

```js
// V8: cache energy field for geodesicRerank (Phase 4)
this.lastEnergyField = accumulatedEnergy;

// Re-bucket: seeds vs emergent
for (const [nid, emergentEnergy] of accumulatedEnergy.entries()) {
    if (allTagsMap.has(nid)) {
        // seed — keep, but max-merge weight (defends against cycle inflation)
        existingTag.adjustedWeight = Math.max(existingTag.adjustedWeight, emergentEnergy);
    } else {
        // emergent — newly activated by topology
        emergentCandidates.push({id: nid, adjustedWeight: emergentEnergy, isPullback: true});
    }
}

emergentCandidates.sort((a, b) => b.adjustedWeight - a.adjustedWeight);
const topEmergent = emergentCandidates.slice(0, MAX_EMERGENT_NODES);
```

After propagation, the `accumulatedEnergy` map is the **complete activation profile** over all tags. Seeds keep `max(originalWeight, propagatedWeight)`; new tags reachable only via spike are bucketed as `emergent` and capped at 50. Capped list is concatenated back into `allTags`.

## Where the boost lands (lines 376-465)

After spike propagation has produced the final `allTags` list with `adjustedWeight` per tag:

```js
// [5] Batch-fetch tag vectors from DB (skip negative ghost ids)
const tagRows = this.db.prepare(`SELECT id, name, vector FROM tags WHERE id IN (...)`).all(...);

// [5.5] Semantic dedup: cosine > 0.88 → merge weights into representative
for (const tag of sortedTags) {
    for (const existing of deduplicatedTags) {
        if (cosine(tag.vector, existing.vector) > 0.88) {
            existing.adjustedWeight += tag.adjustedWeight * 0.2;
            isRedundant = true;
            break;
        }
    }
    if (!isRedundant) deduplicatedTags.push(tag);
}

// [6] contextVec = Σ adjustedWeight_i * tagVector_i, normalized
contextVec[d] = (Σ adjustedWeight_i * tagVector_i[d]) / totalWeight  // weighted mean
contextVec  /= ||contextVec||                                          // L2 normalize

// [6'] Final fuse with query
const alpha = min(1.0, effectiveTagBoost);
fused[d] = (1 - alpha) * originalQuery[d] + alpha * contextVec[d];
fused   /= ||fused||;
return fused;
```

**Final form**: a weighted blend of the original query vector and a tag-context vector, both unit-norm, with `α = min(1, effectiveTagBoost)`. This blended vector replaces the query for downstream similarity search.

`effectiveTagBoost = baseTagBoost * clamp(dynamicBoostFactor, 0.3, 2.0)`. With `baseTagBoost = 0.03` (TagMemoRAG default) and `dynamicBoostFactor` clamped to [0.3, 2.0], the maximum `effectiveTagBoost = 0.06`, well below 1.0. So `α` is small in practice — query is mostly preserved, tag context contributes a few-percent perturbation.

## Total dependency graph (the "what does Phase 1 actually need" surface)

| Source needs | Phase 0 has? | Phase 1 plan |
|---|---|---|
| EPA `project()` returning logicDepth/entropy/dominantAxes | Yes (cold-start identity basis) | Use as-is. Cold-start gives degenerate logicDepth ≈ 1/K but the math still runs |
| EPA `detectCrossDomainResonance()` | No | Stub: return `0`. Affects only `dynamicBoostFactor` slightly |
| ResidualPyramid `analyze()` returning levels+features | No | Substitute with top-K cosine seed selection. Skip layer decay, lang penalty, coverage features |
| `tagCooccurrenceMatrix` | No | **Phase 1 builds this.** |
| `tagIntrinsicResiduals` | Schema yes, values default to 1.0 | Use 1.0 as designed. Wormhole gate degenerates to "edge weight ≥ 1.0" |
| Tag DB rows with vectors | Yes (Phase 0 `tags` table) | Use existing |
| World-view gating, language penalty | No | Skip in Phase 1; revisit when EPA is properly trained |
| Semantic dedup | Yes (cosine is trivial) | Keep as-is, threshold 0.88 |
| Ghost tag injection | No (caller feature) | Skip in Phase 1 |
| Core-tag completion | No | Skip in Phase 1; can add later when API supports core-tag hints |

**Phase 1 minimum viable boost** = (top-K cosine seeds) → (V6 spike propagation through Phase 1 cooc matrix with V7 wormhole gate) → (semantic dedup at 0.88) → (weighted-mean context vector) → (alpha-blend with query, alpha = min(1, baseTagBoost · clamp(logicDepth, 0.3, 2.0))).
