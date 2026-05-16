# 浪潮回归 Phase 3：detectCrossDomainResonance（V6 接通真共振）

## Goal

把 Phase 2b-1 dynamicBoostFactor 公式里的 `resonance = 0` stub（`wave_tag_spike.py:792`）替换为 V6 真实算法 `detectCrossDomainResonance`。让 query 在 EPA basis 上"跨多个非主轴同时强激活"时被识别并放大 dynamic factor。

V7 的 `tag_intrinsic_residuals`（每 tag 在 basis 外分量缓存到 store）**不在本任务范围**，作为后续 Phase 3.5 单独任务。本任务**纯算法接通**：无 store schema 改动，无新 SQL，1-2 天工作量。

## Background / Known Context

### Phase 2b 末态

- `wave_tag_spike._resolve_dynamic_boost_with_world` 的 pyramid 分支：
  ```
  resonance = 0.0  # stub
  dynamic = (logicDepth * (1+log(1+resonance)) / (1+entropy*0.5)) * activation_mult
          * pyramid_post_scale  (floored at epa_floor)
  ```
  `pyramid_post_scale=4.0` 是在 stub=0 假设下 calibrate 的（`scripts/diag_pyramid_dynamic_boost.py` 已 PASS）。
- `EPAProjector.project()` 已 emit `dominantAxes[i] = {label, energy, index, projection}` 与 V6 完全一致（normalized prob，desc-sort，> 0.05 阈值过滤）— 见 `epa_projector.py:41-62`。
- Phase 2b-2 已锁 R10：默认 strategy=constant + 不传 core/ghost ⇒ 8 hashing eval suite + spike-off invariance 字节稳定。本任务**沿用这一兼容性约束**。

### V6 源算法（详见 `research/source-cross-domain-resonance.md`）

`EPAModule.js:170-201`（commit aff66193，repo root，**不在 Plugin/TagMemo/ 子目录**）：

```js
detectCrossDomainResonance(vector) {
    const { dominantAxes } = this.project(vector);
    if (dominantAxes.length < 2) return { resonance: 0, bridges: [] };
    const top = dominantAxes[0];
    const bridges = [];
    for (let i = 1; i < dominantAxes.length; i++) {
        const sec = dominantAxes[i];
        const coActivation = Math.sqrt(top.energy * sec.energy);
        if (coActivation > 0.15) {
            bridges.push({
                from: top.label, to: sec.label,
                strength: coActivation,
                balance: Math.min(top.energy, sec.energy) / Math.max(top.energy, sec.energy),
            });
        }
    }
    return { resonance: bridges.reduce((s, b) => s + b.strength, 0), bridges };
}
```

接入点（TagMemoEngine.js:117, 128, 133）：
```js
const resonance = this.epa.detectCrossDomainResonance(vec);
const resonanceBoost = Math.log(1 + resonance.resonance);
const dynamicBoostFactor = (logicDepth * (1 + resonanceBoost) / (1 + entropyPenalty * 0.5)) * activationMultiplier;
```

### log 域影响范围（参考）

| resonance | log(1+r) | dynamic 增量 |
|---|---|---|
| 0 (聚焦 / cold-start basis) | 0 | × 1 |
| 0.3 | 0.262 | × 1.26 |
| 0.5 | 0.405 | × 1.40 |
| 1.0 | 0.693 | × 1.69 |
| 2.0 | 1.099 | × 2.10 |

## Resolved Decisions

### D1（已锁定 · 2026-05-16）：MVP 只做 detectCrossDomainResonance

- tag_intrinsic_residuals + ResidualPyramid prior 接通 ⇒ **推到 Phase 3.5 单独任务**。
- 本任务范围：1 helper + 接通 + 测试 + 文档 + diag 验证 calibrate（视实测决定是否动 `pyramid_post_scale`）。
- 拒绝两个一起做：scope 过大；store schema 改动 + Pyramid 算法接 prior 是另一组耦合，应单独 brainstorm。

### D2（已锁定 · 2026-05-16）：默认 off

- `wave_phase1.cross_domain_resonance_enabled: bool = False`，与 Phase 2b-2 `lang_penalty_enabled` 同语义。
- 默认 off ⇒ `_resolve_dynamic_boost_with_world` pyramid 分支仍走 `resonance=0` 旧路径，hashing fixture baseline 字节稳定。
- 显式 true ⇒ resonance 接通，可能漂；本任务**接受 `wave_phase1.cross_domain_resonance_enabled=True` 路径上 hashing fixture 的 alpha 漂**，但**default false 路径绝对不漂**（R5 锁底）。
- 拒绝默认 true：与 Phase 2b-2 不一致；漂 baseline 风险大。

### D3（已锁定 · 2026-05-16）：2 个 Histogram metric

- `tagmemorag_tag_resonance_value`（Histogram, labels=`kb_name`，buckets=(0, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2, 2.0, 4.0)）：每次 spike-on + enabled=true 调用后 observe `resonance` 标量。
- `tagmemorag_tag_resonance_bridges_count`（Histogram, labels=`kb_name`，buckets=(0, 1, 2, 3, 5, 8)）：每次 observe `len(bridges)`。
- bridges 完整 list **只进 search_debug_payload**（D5），不上指标避免 from/to label 高基数。
- 拒绝带 bridge label 的 Counter：超 ALLOWED_LABEL_NAMES 集合；tag name 高基数。

### D4（已锁定 · 2026-05-16）：calibrate 看实测决定

- 实施时跑一次 `scripts/diag_pyramid_dynamic_boost.py`（开启 `cross_domain_resonance_enabled=true`，脚本里加 strategy=`pyramid+resonance` 的对照列）。
- 如果 D2 阈值（std > 0.005, range/mean > 0.1）仍 PASS ⇒ 不动 `pyramid_post_scale`。
- 如果 fail ⇒ 重 calibrate（sweep 1.0..6.0 step=0.5，找最小 PASS），更新 config 默认值。
- 拒绝预先 calibrate：可能不必要；hashing cold-start basis label 是 axis-N，能量分布可能就近 0。

### D5（已锁定 · 2026-05-16）：TagBoostInfo 加 2 个数值字段

- 新加 `cross_domain_resonance: float = 0.0` + `cross_domain_bridges_count: int = 0`。
- bridges 完整 list（含 from/to/strength/balance）只在 `search_runtime.search_debug_payload` 的 `tag_boost_debug.cross_domain_bridges` 暴露。
- 拒绝把 bridges 完整 list 进 TagBoostInfo：to_dict 面包过宽；正常路径不需要。

### D6（已锁定 · 2026-05-16）：阈值照搬源

- `coActivation > 0.15` ⇒ module-level 常量 `_RESONANCE_CO_ACTIVATION_THRESHOLD = 0.15`，**不暴露 config**（与源一致，源里就是 hardcode）。
- 拒绝暴露 config：心智膨胀；源默认稳定；如果未来需要调，是 Phase 4+ 的事。

## Requirements

1. **R1（helper 函数）**：在 `wave_tag_spike` 或新模块里加 `detect_cross_domain_resonance(dominant_axes) -> tuple[float, list[dict]]`，按 V6 公式实装。
2. **R2（公式接通）**：`_resolve_dynamic_boost_with_world` 的 pyramid 分支，`cross_domain_resonance_enabled=True` 时把 `resonance=0` 替换为真实计算结果。
3. **R3（公式短路）**：`cross_domain_resonance_enabled=False` 默认 ⇒ `resonance=0` 不变（保持兼容）。
4. **R4（数据契约）**：`TagBoostInfo` 加 `cross_domain_resonance: float / cross_domain_bridges_count: int` 字段；`to_dict` 同步。
5. **R5（向后兼容）**：默认 strategy=constant + cross_domain_resonance_enabled=false ⇒ 8 hashing eval suite + spike-off invariance + 现有 381 段单测全绿。
6. **R6（观测指标）**：D3 的 2 个 Histogram + record 方法 + label contract 同步。
7. **R7（debug payload）**：`search_debug_payload.tag_boost_debug` 加 `cross_domain_bridges: list[dict]` 字段（仅当 enabled=true 且实际 trigger 时填）。
8. **R8（config 字段）**：加 `wave_phase1.cross_domain_resonance_enabled: bool = False` + `config.yaml` 同步。
9. **R9（单测）**：新增 `tests/unit/test_cross_domain_resonance.py`（≥6 段）：dominant<2 / 阈值边界 / 单 bridge / 多 bridge / balance 极值 / 公式接通锁底（resonance=0.5 + log(1.5) ≈ 0.405）；`test_apply_tag_boost.py` 加 1 段 enabled=true 烟雾测。
10. **R10（diag 重 calibrate）**：`scripts/diag_pyramid_dynamic_boost.py` 加 enabled=true 对照列；如 D2 阈值 fail ⇒ 重 calibrate `pyramid_post_scale` + 更新 config 默认 + 注释。
11. **R11（文档）**：README + docs/wave-phase1-architecture.md 加 "Phase 3" 子章节，记录 V6 公式 + 阈值 0.15 + 默认 off + log 域增益参考表。

## Acceptance Criteria

- [ ] AC1：`detect_cross_domain_resonance(dominant_axes=[])` 返回 `(0.0, [])`；`len < 2` 同样。
- [ ] AC2：单 bridge 锁底：`top.energy=0.5, sec.energy=0.5` ⇒ `coActivation=0.5 > 0.15` ⇒ resonance=0.5；balance=1.0。
- [ ] AC3：阈值边界锁底：`top=0.5, sec=0.04` ⇒ `coActivation=sqrt(0.02)≈0.141 < 0.15` ⇒ 不进 bridges；resonance=0。
- [ ] AC4：多 bridge 求和锁底：3 个 axis energy=[0.5, 0.4, 0.3] ⇒ bridges=[(0,1)=sqrt(0.20), (0,2)=sqrt(0.15)]，resonance=sqrt(0.20)+sqrt(0.15)≈0.834。
- [ ] AC5：`cross_domain_resonance_enabled=False`（默认） ⇒ `_resolve_dynamic_boost_with_world` 输出与 Phase 2b-1 完全一致（数学锁底）。
- [ ] AC6：`enabled=True` + 假 EPA projection 给 dominantAxes ⇒ dynamicBoostFactor 按公式 `× (1 + log(1+resonance))` 缩放。
- [ ] AC7：默认 strategy=constant + 不传 core/ghost + cross_domain_resonance_enabled=false ⇒ 8 hashing eval suite + e2e baseline invariance + 现有单测全绿（381 + 新增 ~7 = ~388）。
- [ ] AC8：`enabled=true` 在 hashing fixture 上的 alpha 漂幅可量化记录（diag 输出包含），但 D2 阈值（std > 0.005, range/mean > 0.1）仍 PASS（必要时重 calibrate `pyramid_post_scale`）。
- [ ] AC9：2 个 metric 在 spike-on + enabled=true 调用后实际写入；`test_observability_metrics.py` 加 1 段。
- [ ] AC10：search_debug_payload.tag_boost_debug 包含 `cross_domain_bridges`（list[dict]）当且仅当实际触发；TagBoostInfo 字段更新到 to_dict。
- [ ] AC11：README + docs/wave-phase1-architecture.md 加 Phase 3 段落（含 log 域增益参考表 + 默认 off 说明）。

## Definition of Done

- 1 helper + 接通 + 5 段单测 + 1 段烟雾测 + 1 段 metric 测 + 文档段落
- pytest 全绿（约 388 段）；run_eval_ci 8 suites pass；e2e baseline invariance 字节稳定
- diag_pyramid_dynamic_boost.py 重 calibrate 后（若需要）overall PASS 在 enabled=true 列
- `pyramid_post_scale` 默认值要么不变（diag PASS）要么更新（diag PASS）
- AC1-AC11 全勾

## Out of Scope（明确不做，由 Phase 3.5 / 4 接）

- **tag_intrinsic_residuals 训练 + 缓存 store**（Phase 3.5）
- **ResidualPyramid 接 residual prior**（Phase 3.5 附属）
- 实时正交性 worldview gating（Phase 2b-2 决策不做）
- V8 geodesicRerank（Phase 4）
- siliconflow.json 生产 baseline 重训（独立生产 readiness 任务）
- ghost server-side encode（Phase 2b-2 决策不做）
- 暴露 `coActivation` 阈值到 config（D6 锁不做）

## Decision Log (ADR-lite)

- **D1**：MVP 只做 detectCrossDomainResonance；tag_intrinsic_residuals 推 Phase 3.5
- **D2**：`cross_domain_resonance_enabled: bool = False` 默认 off
- **D3**：2 个 Histogram metric（resonance value + bridges count），不带 bridge label
- **D4**：post_scale 看实测，diag 不 PASS 才重 calibrate
- **D5**：TagBoostInfo 加 2 个数值字段；bridges list 只进 search_debug_payload
- **D6**：`coActivation > 0.15` 阈值照搬源 hardcode，不暴露 config

## Research References

- [`research/source-cross-domain-resonance.md`](research/source-cross-domain-resonance.md) — V6 EPAModule.js:170-201 detectCrossDomainResonance 逐行解析 + dynamicBoostFactor 接入点 + Python 移植细节
- Phase 2b-1 [`archive/2026-05/05-15-wave-phase2b-residualpyramid/research/source-residual-pyramid.md`](../archive/2026-05/05-15-wave-phase2b-residualpyramid/research/source-residual-pyramid.md) — pyramid 接口契约（caller 调用点）
- Phase 2b-2 [`archive/2026-05/05-15-wave-phase2b2-worldview-langpenalty-ghost/research/source-worldview-langpenalty-ghost.md`](../archive/2026-05/05-15-wave-phase2b2-worldview-langpenalty-ghost/research/source-worldview-langpenalty-ghost.md) — Phase 2b 公式末态
