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


## Session 3: Wave Phase 3: detectCrossDomainResonance (V6 真共振接通)

**Date**: 2026-05-16
**Task**: 浪潮回归 Phase 3：detectCrossDomainResonance（V6 接通真共振）
**Branch**: `feat/wave-phase1-cooccurrence-spike`

### Summary

Phase 3 把 Phase 2b-1 dynamicBoostFactor 公式里的 `resonance = 0` stub 替换为 V6 真实算法 `detectCrossDomainResonance`（端口自 lioensky/VCPToolBox EPAModule.js:170-201, commit aff66193）。新 helper 落在 `wave_tag_spike` 内：对 EPA `dominantAxes` 的每个非主轴对 sqrt 几何平均，> 0.15 阈值（hardcode，与源一致）的进 bridges；resonance = sum(strength) 喂给 `log(1+resonance)` 项。默认 `cross_domain_resonance_enabled=False` 保持 Phase 2b-2 行为字节稳定；显式开启时 hashing fixture 上 resonance mean=0.76 / std=0.12，pyramid_post_scale=4.0 不需要 recalibrate（diag overall PASS）。新增 `TagBoostInfo.cross_domain_resonance / cross_domain_bridges_count`（入 to_dict）+ 私有 `_cross_domain_bridges`（不入 to_dict，仅 search_debug_payload 在 trigger 时暴露 `cross_domain_bridges` 列表）。新增 2 个 Histogram metric (`tag_resonance_value` / `tag_resonance_bridges_count`)，仅 enabled=true 时 record。新增 `tests/unit/test_cross_domain_resonance.py` 14 段 + 现有单测扩 ~7 段；总 pytest 402 passed (+21), 8/8 hashing eval suites pass, e2e baseline invariance 2/2, diag overall PASS（含 pyramid+resonance 列）。

### Main Changes

- `src/tagmemorag/wave_tag_spike.py`: `_RESONANCE_CO_ACTIVATION_THRESHOLD` + `detect_cross_domain_resonance` helper；`_DynamicBoostResult` 扩 `resonance` / `bridges`；pyramid 分支按 `cross_domain_resonance_enabled` 接通；`TagBoostInfo` 加 3 个字段（含 1 个私有 bridges tuple）。
- `src/tagmemorag/config.py` + `config.yaml`: `WavePhase1Config.cross_domain_resonance_enabled = False`。
- `src/tagmemorag/observability/metrics.py`: 2 个 Histogram + 2 个 record 方法。
- `src/tagmemorag/search_runtime.py`: `search_debug_payload` 扩 `tag_boost_debug.cross_domain_bridges`，仅 bridges 非空时填。
- `scripts/diag_pyramid_dynamic_boost.py`: 新增 `pyramid+resonance` 第 4 列对照；resonance/bridges 序列统计；PASS gate 同时应用到该列。
- README + docs/wave-phase1-architecture.md: 新增 "Cross-domain resonance (Phase 3)" 段（log 域增益参考表、阈值 0.15 来源、debug payload schema、Phase 3.5 / 4 路线提示）。

### Git Commits

| Hash | Message |
|------|---------|
| (pending) | feat(wave-phase3): detectCrossDomainResonance + log-domain dynamicBoostFactor |

### Testing

- [OK] pytest -q: 402 passed, 2 skipped (was 381 / 2 before)
- [OK] run_eval_ci.py: 8/8 hashing eval suites pass
- [OK] tests/e2e/test_search_baseline_invariance.py: 2/2
- [OK] scripts/diag_pyramid_dynamic_boost.py: overall PASS (pyramid + pyramid+resonance both PASS at default post_scale=4.0)

### Status

[OK] **Completed** — AC1-AC11 all green; default off (`cross_domain_resonance_enabled: false`).

### Next Steps

- Phase 3.5: train real `tag_intrinsic_residuals` and feed them into ResidualPyramid as a prior.
- Production rollout decision (flip the flag) waits on real EPA basis labels in siliconflow.


## Session 3: Phase 4: V8 geodesicRerank 接入

**Date**: 2026-05-16
**Task**: Phase 4: V8 geodesicRerank 接入
**Branch**: `feat/wave-phase1-cooccurrence-spike`

### Summary

Port V8 geodesicRerank as wave 主线最后一块。10 stage 闭环：4 个新 settings (默认 false)、TagBoostInfo.accumulated_energy 透传 spike 能量场、wave_search.rerank_pool_size 支持过采样、wave_geodesic_rerank.py 纯函数算法 + 三层退化、4 项 metric (applied/skipped{12 reasons}/swap{3 kinds}/hit_count)、execute_search 接入 + skipped 细分、diag 脚本 PASS gate (本仓 fixture applied=100% / max_geo_zero=0% / hit_p50=3 / swap=4.7/q)、run_eval_ci.py --geodesic informational 列、文档 + spec 同步。Check 期顺手补 consumer label 漏 (Phase 3.5 遗留)、reason label 入白名单。435 passed / 8 套 hashing eval flag-off 字节稳定。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `4e51225` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: siliconflow baseline 工具链 + informational baseline

**Date**: 2026-05-17
**Task**: siliconflow baseline 工具链 + informational baseline
**Branch**: `feat/wave-phase1-cooccurrence-spike`

### Summary

为 wave readiness 准备生产 embedder 对照基线。build_eval_baseline 改 model 到 Qwen/Qwen3-VL-Embedding-8B (4096维) + smoke test (key/401/403/404/dim 各分类提示) + 指数退避重试 (1/2/4/8/16s, 4xx 短路) + --compare-with delta 表 + atomic write。run_eval_ci 加 --embedder hashing|siliconflow + --no-default-thresholds (跳过项目级 0.8 floor，case-level fixture 阈值仍生效)。siliconflow.json 落盘但定位为 informational reference (7/8 套比 hashing 差 14-80%，根因在 fixture ground truth 是 hashing-self-circular 标注；wave_phase1 参数也按 dim=64 调过)。10 个新单测覆盖 retry 5 个分支 + atomic write + delta 表。445 passed (+10) / hashing CI 默认 path 全 8 套字节稳定。Phase 4 archive 残影顺手清理。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `d840c1e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
