# Journal - suixingchen (Part 1)

> AI development session journal
> Started: 2026-05-10

---



## Session 1: Wave Phase 1: cooccurrence matrix + V6 spike propagation

**Date**: 2026-05-15
**Task**: Wave Phase 1: cooccurrence matrix + V6 spike propagation
**Branch**: `master`

### Summary

Phase 1 ships the per-KB directed cooccurrence matrix builder and V6 LIF spike propagation behind wave_phase1.spike_enabled (default false). Adds tag_cooccurrence.py + wave_tag_spike.py with byte-for-byte port of VCPToolBox srConfig defaults; wires apply_tag_boost into search_runtime; threads tag_cooccurrence_edges/error through the Rebuild data path; adds 3 low-cardinality Prometheus metrics; baseline rebuilt under spike-on (numerically identical to Phase 0 — alpha=0.03 too small to shift top-K at fixture scale). 50+ new unit tests, 332/2 pass. Decision D6 added: CI and baseline both lock spike-on so quality gate guards the new algorithm. Soft rollback: flip spike_enabled=false. Hard rollback: rm -rf data/_global/tag_cooccurrence/.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `8ca0965` | (see git log) |
| `c862c22` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: Wave Phase 2b: ResidualPyramid + V6 external modulators

**Date**: 2026-05-16
**Task**: Wave Phase 2b: ResidualPyramid + V6 external modulators
**Branch**: `feat/wave-phase1-cooccurrence-spike`

### Summary

Phase 2b-1: multi-level Gram-Schmidt residual pyramid as strategy=pyramid seed selector + full V6 dynamicBoostFactor formula (logicDepth × resonance / entropy × activation_mult × pyramid_post_scale, calibrated to 4.0). Phase 2b-2: V6 4 peripheral modulators wired to pyramid path — dynamicCoreBoostFactor [1.20..1.40], per-tag coreBoost via individualRelevance, langPenalty (technical-noise / cross-domain / social regex matrix), core completion (SQL-pull missing core_tags), ghost injection (caller vectors with negative ids + dim mismatch skip). SearchRequest exposes core_tags + ghost_tags (GhostTagSpec); cache key threads them through. tag_governance.resolve_tag reused for synonym→canonical. 3 new Prometheus metrics (tag_lang_penalty_applied / tag_core_tags_resolved / tag_ghosts_injected). All defaults preserve hashing-fixture invariance (lang_penalty_enabled=false). Verification: pytest 381 passed (+27), 8/8 hashing eval suites pass, e2e baseline invariance 2/2, diag_pyramid_dynamic_boost overall PASS.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `07bdf93` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
