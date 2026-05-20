# Source: V6 detectCrossDomainResonance 逐行解析

> 抓取 `lioensky/VCPToolBox` 主分支 `EPAModule.js`（commit aff66193，repo root，**不在 Plugin/TagMemo/ 子目录下**）。
> 配套消费方在 `TagMemoEngine.js` 同 commit。
> 抓取日期：2026-05-16。

源 URL：
- https://github.com/lioensky/VCPToolBox/blob/aff66193/EPAModule.js#L170
- https://github.com/lioensky/VCPToolBox/blob/aff66193/TagMemoEngine.js#L117

---

## 1. detectCrossDomainResonance（EPAModule.js:170-201）

```js
detectCrossDomainResonance(vector) {
    const { dominantAxes } = this.project(vector);
    if (dominantAxes.length < 2) return { resonance: 0, bridges: [] };

    const bridges = [];
    const topAxis = dominantAxes[0];

    // 只检查与最强轴共振的其他轴
    for (let i = 1; i < dominantAxes.length; i++) {
        const secondaryAxis = dominantAxes[i];

        // 几何平均能量： sqrt(E1 * E2)
        // 这代表两个轴同时被激活的程度。如果一个极强一个极弱，乘积会很小。
        const coActivation = Math.sqrt(topAxis.energy * secondaryAxis.energy);

        // 只有当共激活强度足够大时，才视为"共振"
        if (coActivation > 0.15) {
            bridges.push({
                from: topAxis.label,
                to: secondaryAxis.label,
                strength: coActivation,
                // Distance 在这里是隐喻，因为轴是正交的，距离恒定。
                // 我们可以用能量比率来表示"平衡度"
                balance: Math.min(topAxis.energy, secondaryAxis.energy)
                       / Math.max(topAxis.energy, secondaryAxis.energy)
            });
        }
    }

    // 总共振值 = 所有 Bridge 强度的总和
    const resonance = bridges.reduce((sum, b) => sum + b.strength, 0);
    return { resonance, bridges };
}
```

### 关键观察

1. **`dominantAxes[i].energy` = normalized probability** — `(projection_k^2) / totalEnergy`，已 sort desc。最大值 ≤ 1.0；只有 `probabilities[k] > 0.05` 才进 dominantAxes（EPAModule.js:144）。
2. **公式核心**：`bridge.strength = sqrt(top.energy × sec.energy)` 是几何平均，反映 "两个轴同时被激活的程度"。
3. **硬编码阈值** `coActivation > 0.15`（≡ `top × sec > 0.0225`）。源里**没有走 config**，是写死的常量。
4. **dominantAxes < 2 直接返 0**：cold-start basis（K=1）或极聚焦 query 不会触发。
5. **resonance 上界**：理论 ≤ K-1（每个非主轴最多贡献 1.0），实际由 `> 0.15` 阈值 + EPA basis 数量决定。Phase 2b-1 默认 K=8，max ≈ 7。
6. **`bridges` 列表**：包含 from/to label、strength、balance；可用于诊断（dashboard / debug payload），不影响公式输出。

---

## 2. 在 dynamicBoostFactor 公式里的接入点（TagMemoEngine.js:115-135）

```js
const epaResult = this.epa.project(originalFloat32);
const { logicDepth, entropy: entropyPenalty, dominantAxes } = epaResult;

const resonance = this.epa.detectCrossDomainResonance(originalFloat32);
// ...
const activationMultiplier = ...;
const resonanceBoost = Math.log(1 + resonance.resonance);   // ← 接入点
// ...
const dynamicBoostFactor = (logicDepth * (1 + resonanceBoost)
                            / (1 + entropyPenalty * 0.5)) * activationMultiplier;
```

`resonance.resonance` 是个标量（sum of bridge strengths），喂给 `Math.log(1 + ...)`。

### log 域影响范围

| resonance 值 | log(1+resonance) | dynamic 增量 |
|---|---|---|
| 0 (cold-start / 极聚焦) | 0 | × 1 |
| 0.3 (一对中等共激活) | 0.262 | × 1.26 |
| 0.5 (一对强共激活) | 0.405 | × 1.40 |
| 1.0 (一对极强 + 几个中等) | 0.693 | × 1.69 |
| 2.0 (多 axis 同时激活) | 1.099 | × 2.10 |

⇒ **log 域增益最多 2-3x**，但因 hashing fixture K=10 / cold-start basis label 类似 "axis-N" 都属于技术世界，实际 fixture 上 resonance 可能仍接近 0。**TagMemoRAG 端测算后再 calibrate `pyramid_post_scale`**。

---

## 3. 与 TagMemoRAG 现状的契合度

| 源依赖 | TagMemoRAG 现状 | 移植决策 |
|---|---|---|
| `dominantAxes[i].energy` (normalized prob) | ✅ 已实现 (epa_projector.py:49) | 直接读 |
| `dominantAxes[i].label` | ✅ 已实现 (epa_projector.py:48) | 直接读 |
| `dominantAxes` desc-sorted | ✅ 已实现 (epa_projector.py:54) | 直接读 |
| `> 0.05` 阈值进 dominant | ✅ 已实现 (epa_projector.py:53) | 与源一致 |
| `coActivation > 0.15` 阈值 | 没有 | **新加 module-level 常量**；不暴露 config（与源一致） |
| `resonance` 接入 dynamicBoostFactor | ❌ 当前 `wave_tag_spike.py:792` `resonance = 0.0` stub | 改为调 `detect_cross_domain_resonance(projection)` |
| `bridges` 诊断字段 | 没有 | 写到 `TagBoostInfo.cross_domain_bridges_count`（数量够用，不需要全字符串）+ 或写到诊断 payload |

---

## 4. Python 移植细节

```python
import math
from typing import Sequence, Mapping

# 与源一致的硬编码阈值（V6 EPAModule.js:186）
_RESONANCE_CO_ACTIVATION_THRESHOLD = 0.15


def detect_cross_domain_resonance(
    dominant_axes: Sequence[Mapping[str, object]],
) -> tuple[float, list[dict]]:
    """V6 detectCrossDomainResonance port.

    Source: lioensky/VCPToolBox EPAModule.js:170-201.

    Args:
        dominant_axes: list of {"label": str, "energy": float, "index": int, "projection": float},
                       desc-sorted by energy. Output of `EPAProjector.project()["dominantAxes"]`.

    Returns:
        (resonance_total, bridges) where:
          - resonance_total = sum(bridge.strength), used by dynamicBoostFactor as log(1+resonance)
          - bridges = list of {from, to, strength, balance} dicts (diagnostics only)
    """
    if len(dominant_axes) < 2:
        return 0.0, []
    top = dominant_axes[0]
    top_energy = float(top.get("energy", 0.0))
    top_label = str(top.get("label", ""))
    bridges: list[dict] = []
    for sec in dominant_axes[1:]:
        sec_energy = float(sec.get("energy", 0.0))
        co_act = math.sqrt(max(0.0, top_energy * sec_energy))
        if co_act > _RESONANCE_CO_ACTIVATION_THRESHOLD:
            sec_label = str(sec.get("label", ""))
            balance = (
                min(top_energy, sec_energy) / max(top_energy, sec_energy)
                if max(top_energy, sec_energy) > 1e-12
                else 0.0
            )
            bridges.append({
                "from": top_label,
                "to": sec_label,
                "strength": co_act,
                "balance": balance,
            })
    return sum(float(b["strength"]) for b in bridges), bridges
```

接入点（`wave_tag_spike._resolve_dynamic_boost_with_world` pyramid 分支）：

```python
# 替换 line 792:
# resonance = 0.0  # D3 stub
resonance, bridges = detect_cross_domain_resonance(projection.get("dominantAxes", []))
# 后续 line 800:
resonance_term = math.log(1.0 + resonance)
```

---

## 5. 默认值与产线策略

源没有把任何 resonance 阈值暴露到 config — TagMemoRAG **沿用此**：
- `coActivation > 0.15` ⇒ module-level 常量 `_RESONANCE_CO_ACTIVATION_THRESHOLD = 0.15`
- 公式系数（`log(1 + ...)`）⇒ 按源照搬

**Phase 3 产线策略**：
- 加 `wave_phase1.cross_domain_resonance_enabled: bool = False` 总开关，**默认 off**（与 Phase 2b-2 同语义，不漂 baseline）。
- 仅当显式 `enabled=true` ⇒ resonance 真触发；否则 `_resolve_dynamic_boost_with_world` 仍走 `resonance=0` 旧路径。
- 接通后**必然要重 calibrate `pyramid_post_scale`** —— `diag_pyramid_dynamic_boost.py` 重跑确认 D2 阈值仍 PASS。

## 6. 与 Phase 2b-1 测试的兼容

- `tests/unit/test_epa_logic_depth.py` 5 段 pyramid 测试 fixture 用 cold-start basis（K=1 标签 axis-0）：`dominantAxes` 长度 = 1 ⇒ `detect_cross_domain_resonance` 直接返 0 ⇒ Phase 3 接通后**测试输出字节稳定**。
- hashing fixture（K=10, 12 tag）：dominantAxes 多 axis 但能量分布如何不确定 — 跑一次 diag 看实际 resonance 分布，不必在 PRD 阶段预测。
