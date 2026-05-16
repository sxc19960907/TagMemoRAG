# Source: ResidualPyramid.js（V3.7 / Physics-Optimized Edition）

> 逐行抓取 `lioensky/VCPToolBox` 主分支的 `ResidualPyramid.js`（394 行）+ `TagMemoEngine.js` 调用点，给 Python 端 Phase 2b-1 的"移植深度选择"做依据。Phase 1 research/source-tag-boost-and-spike.md 是上层接口视角；本文补齐**算法内核**、**配置项**、**外部依赖**、**Python 移植 surface 选项**。

源 URL：
- ResidualPyramid.js：https://github.com/lioensky/VCPToolBox/blob/main/ResidualPyramid.js
- TagMemoEngine.js（调用方）：https://github.com/lioensky/VCPToolBox/blob/main/TagMemoEngine.js
- TAGMEMO_TUNING_GUIDE.md（参数手册）：https://github.com/lioensky/VCPToolBox/blob/main/TAGMEMO_TUNING_GUIDE.md

---

## 1. Constructor & Config（ResidualPyramid.js:7-19）

```js
class ResidualPyramid {
    constructor(tagIndex, db, config = {}) {
        this.tagIndex = tagIndex;
        this.db = db;
        this.config = {
            maxLevels: config.maxLevels || 3,
            topK: config.topK || 10,
            minEnergyRatio: config.minEnergyRatio || 0.1,  // 残差/原始 < 0.1 即停（解释了 90%）
            dimension: config.dimension || 3072,
            ...config
        };
    }
}
```

**3 个关键 knob**：
- `maxLevels = 3`：金字塔最多 3 层。
- `topK = 10`：每层从 tagIndex 召回 top-10 邻居 tag。
- `minEnergyRatio = 0.1`：剩余残差能量占原始能量比例 < 10% 时早停。

源 dimension 默认 3072（OpenAI text-embedding-3-large）；TagMemoRAG hashing dim=64。

外部依赖（**这是 Python 移植的关键约束**）：
- `tagIndex`：Rust HNSW（VexusIndex）。提供 `search(vec, topK)`（必选）+ 可选 `computeOrthogonalProjection` / `computeHandshakes`（Rust 加速路径）。后两个有 JS fallback。
- `db`：SQLite，用 `_getTagVectors(ids)` 拉 `tags.id, name, vector` 行。

TagMemoEngine 实例化时只传 `dimension`，其它都默认（TagMemoEngine.js:38-40）：
```js
this.residualPyramid = new ResidualPyramid(this.tagIndex, this.db, {
    dimension: this.config.dimension
});
```
⇒ **生产侧实际跑 maxLevels=3 / topK=10 / minEnergyRatio=0.1**。Python 端可以照搬。

---

## 2. analyze(queryVector) 主循环（ResidualPyramid.js:25-122）

```
输入：query 向量（dim 维）
输出：{
    levels: [{level, tags, projectionMagnitude, residualMagnitude,
              residualEnergyRatio, energyExplained, handshakeFeatures}, ...],
    totalExplainedEnergy: float,    // sum of energyExplained over levels
    finalResidual: Float32Array,    // 最后一层 residual
    features: {depth, coverage, novelty, coherence, tagMemoActivation, expansionSignal}
}
```

主流程：
1. 算原始能量 `originalEnergy = ||query||^2`。退化（< 1e-12）⇒ 返 `_emptyResult`（features 全 0，`tagMemoActivation=0`）。
2. `currentResidual = query.copy()`。
3. for level in 0..maxLevels:
   1. **召回**：`tagIndex.search(currentResidual, topK)` → 拿候选 tag id + similarity score。失败/空 ⇒ break。
   2. **拉向量**：`db.SELECT id, name, vector FROM tags WHERE id IN (...)`。
   3. **Gram-Schmidt 投影**：把 currentResidual 投到 tag 张成的子空间 → 得 `{projection, residual, basis, basisCoefficients}`（详见 §3）。
   4. **能量**：`energyExplainedByLevel = (||currentResidual||² - ||residual||²) / originalEnergy`。
   5. **Handshakes**：query 跟每个 tag 的 delta 向量统计，提取 `directionCoherence` / `patternStrength` / `noveltySignal` / `noiseSignal`（详见 §4）。
   6. push level 记录到 pyramid.levels。
   7. `currentResidual ← residual`，更新到下一轮。
   8. **早停**：`residualEnergy / originalEnergy < minEnergyRatio` ⇒ break。
4. `pyramid.finalResidual = currentResidual`。
5. `pyramid.features = _extractPyramidFeatures(pyramid)`（§5）。

---

## 3. Gram-Schmidt 正交投影（ResidualPyramid.js:128-207）

输入 `(vector, tags)`，输出 `{projection, residual, orthogonalBasis, basisCoefficients}`。

**Modified Gram-Schmidt**（数值稳定版）：

```python
# Python 等价
basis = []                                # list of unit vectors
basis_coeffs = np.zeros(n)

for i in range(n):
    v = tags[i].vector.copy()
    # 减去在已有基上的投影
    for u in basis:
        v -= np.dot(v, u) * u
    mag = np.linalg.norm(v)
    if mag > 1e-6:
        v /= mag
        basis.append(v)
        basis_coeffs[i] = abs(np.dot(query_vec, v))   # query 在 u_i 上的绝对贡献
    # 否则该 tag 与已有基线性相关 → coeff=0

# 总投影：query 在子空间上的投影
projection = sum(np.dot(vector, u) * u for u in basis)
residual = vector - projection
```

**关键性质**：
- `basis_coeffs[i]` 是 **该 tag 对解释能量的贡献度**（不是 softmax 权重；顺序敏感但比 softmax 准）。这就是源里 `tags[i].contribution` 字段的来源。
- 线性相关 tag 的 `basis_coeffs[i] = 0`（被前序 tag 完全解释）。
- 正交投影性质：`||currentResidual||² = ||projection||² + ||residual||²`，能量守恒，所以 §2.3.iv 那个减法永远 ≥ 0。
- Rust 加速路径（line 132-154）：JS 实现是 fallback；Python 端没有这个二选一负担，直接 numpy 即可。

---

## 4. Handshakes（ResidualPyramid.js:213-265 + _analyzeHandshakes:271-312）

**Handshake = query 与每个 tag 的差向量** `delta_i = query - tag_i.vector`。

```python
def compute_handshakes(query, tags):
    # delta_i 和归一化方向
    deltas = [query - tag.vector for tag in tags]
    magnitudes = [np.linalg.norm(d) for d in deltas]
    directions = [d / mag if mag > 1e-9 else np.zeros(dim) for d, mag in zip(deltas, magnitudes)]
    return magnitudes, directions
```

**统计特征**（`_analyzeHandshakes`）：
1. **directionCoherence**：所有 direction 的均值向量长度。`||mean(direction_i)||`
   - 高 ⇒ 所有 tag 都向同一方向偏离 query（query 在 tag 簇 "外部"）
   - 低 ⇒ tag 包围 query（query 在已知领域 "中间"）
2. **patternStrength**：前 5 个方向两两点积绝对值的均值。tag 之间方向是否相似。
3. **noveltySignal = directionCoherence**（line 307）。
4. **noiseSignal = (1 - directionCoherence) * (1 - avgPairwiseSim)**（line 310）。

---

## 5. _extractPyramidFeatures（ResidualPyramid.js:317-352）

**输出 features dict 6 个字段**：

```python
def _extract_features(pyramid):
    if not pyramid.levels:
        return dict(depth=0, coverage=0, novelty=1, coherence=0, tagMemoActivation=0)

    handshake = pyramid.levels[0].handshakeFeatures   # 只用 level-0 的
    coverage = min(1.0, pyramid.totalExplainedEnergy)
    coherence = handshake.patternStrength if handshake else 0
    residual_ratio = 1 - coverage
    directional_novelty = handshake.noveltySignal if handshake else 0
    novelty = residual_ratio * 0.7 + directional_novelty * 0.3
    noise = handshake.noiseSignal if handshake else 0

    return dict(
        depth=len(pyramid.levels),
        coverage=coverage,
        novelty=novelty,
        coherence=coherence,
        tagMemoActivation=coverage * coherence * (1 - noise),  # ★ 进 dynamicBoostFactor 公式
        expansionSignal=novelty,
    )
```

**caller 真用上的 2 个字段**（TagMemoEngine.js:87, 96）：
- `features.tagMemoActivation`：进 `activationMultiplier = 0.5 + activation * 1.0`（默认 actRange=[0.5,1.5]）。
- `features.coverage`：进 `coreMetric = logicDepth*0.5 + (1-coverage)*0.5`。

`novelty / coherence / depth / expansionSignal` **只用于 debug log**（line 100-103），不进算法。⇒ Python 端可以 features-minimal 实现。

---

## 6. levels[i].tags 的 schema（ResidualPyramid.js:87-100）

```python
levels[i].tags = [
    {
        "id": int,
        "name": str,
        "similarity": float,        # tagIndex.search 返的 score（cosine）
        "contribution": float,      # basisCoefficients[i] 的绝对值
        "handshakeMagnitude": float,
    }
    for i, t in enumerate(rawTags)
]
```

caller 用法（TagMemoEngine.js:132-180）：
- `t.contribution || t.weight || 0` 当 `adjustedWeight` 的种子（line 177）。⇒ **核心字段**。
- `t.similarity` 用于核心 tag 的 `individualRelevance`（line 144）→ Phase 2b-2 范围。
- `t.handshakeMagnitude`、`level.handshakeFeatures` **caller 不读**（只在 features 提取时用了 level-0）。

⇒ Python 端 levels 输出**最少需要 `id / name / contribution`**，再带 `similarity` 给 2b-2 用即可，handshake 字段可以全砍。

---

## 7. 与 EPAModule 的关系

EPAModule 也用 tagIndex（VexusIndex），但 **basis 完全独立**。EPAModule 用的是 PCA/cold-start 训出的全局 K 维基，ResidualPyramid 是**每次 query 现训**：每层 `tags = tagIndex.search(query, K)` → 这 K 个 tag 张成临时子空间 → Gram-Schmidt 算正交投影。

所以：
- ResidualPyramid 与 EPAModule 不共享 basis；ResidualPyramid 是 query-time per-level dynamic basis。
- 移植时**不依赖** Phase 0 的 `epa_basis.npz`。
- 数据依赖只是 `tags.vector` BLOB（TagMemoRAG Phase 0 schema 已有）。

---

## 8. Python 端可选移植深度

| 档位 | 内容 | 输出 features | 输出 levels[].tags 字段 | LOC 估计 | 能否产 dynamicBoostFactor 公式所需的 tagMemoActivation/coverage |
|---|---|---|---|---|---|
| **L1 最小可用** | 多级 Gram-Schmidt + coverage 公式 + 简化 tagMemoActivation（不算 handshake，直接 `tagMemoActivation = coverage`） | depth, coverage, tagMemoActivation | id, name, contribution, similarity | ~120 | ✅（但 tagMemoActivation 退化为 coverage，不带 coherence/noise 调制） |
| **L2 中等** | L1 + level-0 handshake + 完整 tagMemoActivation 公式 | + coherence, novelty, noise | + handshakeMagnitude（level-0 only） | ~180 | ✅（完整公式，包含 coherence/noise） |
| **L3 完整 1:1** | 所有 levels 都算 handshake + 全 features | 全部 6 字段 | 全部 5 字段 | ~250 | ✅ |

**推荐 L2**：`tagMemoActivation = coverage * coherence * (1 - noise)` 是 caller 唯一用的公式；只在 level-0 算 handshake 就够（features 提取本来也只读 `pyramid.levels[0].handshakeFeatures`，line 322）。L3 多算的 handshake 在源里也是**只 debug log 用**。

L1 → L2 增量是 ~60 行，但 `tagMemoActivation` 从"等于 coverage"升级到"含相干性/噪音调制"。若诊断显示 hashing dim=64 上 coherence 噪音过大，可临时退到 L1（`coherence=1, noise=0`）。

---

## 9. TagMemoRAG Python 端实现要点

### 9.1 数据来源

源 `tagIndex.search(query, topK)` ≈ Python 端**全量扫 SQLite `tags(kb_name, vector)` 取 top-K cosine**。当前 `wave_tag_spike._select_seeds`（src/tagmemorag/wave_tag_spike.py:248-270）已经做这个；可以直接复用 + 调 topK。规模：Phase 1 fixture 12 tags / 生产侧 ≤ 1 万 tags / 每层一次 → 完全够用。

### 9.2 Per-KB vs Global

源没有 kb_name 概念。Phase 1 D8 决策"per-KB cooccurrence matrix"，ResidualPyramid 也应**per-KB**：每次 `analyze` 只在当前 KB 的 tag 池里召回。

### 9.3 与 Phase 1 `_select_seeds` 的关系

Phase 1 现在的 `_select_seeds` = single-level top-K cosine，作为 ResidualPyramid 的 option (b) substitute（Phase 1 research 里点名）。Phase 2b-1 把它替换为 `ResidualPyramid.analyze().levels[*].tags`，每个 level 都喂入 `apply_tag_boost` candidate 列表，带 `layerDecay = 0.7^level`。

### 9.4 退化路径

- query 全零 / `originalEnergy < 1e-12` ⇒ 返回 `_emptyResult`（caller 已经在 line 322-329 兜底 `levels=[]` 时返 features 全 0）。Python 端要复刻。
- tagIndex.search 失败 / 返空 ⇒ 当前层 break，但 pyramid 继续返已有 levels。
- Gram-Schmidt 全部线性相关 ⇒ basis_coeffs 全 0，contribution 全 0，level 仍记录但贡献 0。

### 9.5 pyramid features 与 dynamicBoostFactor 公式的接通

```
[公式接通] (TagMemoEngine.js:86-91)
actRange = [0.5, 1.5]                                        # config.activationMultiplier
activationMultiplier = actRange[0] + features.tagMemoActivation * (actRange[1]-actRange[0])
dynamicBoostFactor = (logicDepth * (1 + log(1+resonance)) / (1 + entropy*0.5)) * activationMultiplier
effectiveTagBoost  = baseTagBoost * clamp(dynamicBoostFactor, [0.3, 2.0])
```

Python 端 Phase 2b-1：
- `logicDepth` ← `EPAProjector.project(query)["logicDepth"]`（已在 Phase 0/2a 实现）
- `entropy`    ← `EPAProjector.project(query)["entropy"]`（实现里叫 `normalized_entropy`，已返 dict）
- `resonance`  ← stub `0.0`（Phase 2b 不移植 `EPA.detectCrossDomainResonance()`，写明 Out of Scope）
- `features.tagMemoActivation` ← ResidualPyramid 产
- `features.coverage` ← ResidualPyramid 产（用于 coreMetric，Phase 2b-2 范围；Phase 2b-1 先存上不用）

⇒ Phase 2a 的 `epa_logic_depth_scale` / `epa_floor` 字段在新公式接通后**语义改变**。两个选择：
- (a) 保留两个字段，接到新公式上做 `dynamicBoostFactor *= scale`，`max(floor, ...)`。
- (b) 标 deprecated（仍读 config 但 warn），只走 source 形态。

Phase 2b-1 brainstorm 时再决定（PRD Q3）。

---

## 10. 配置项总表（Phase 2b-1 要在 `wave_phase1` 加的字段）

```yaml
wave_phase1:
  # —— 已有 ——（Phase 0/1/2a）
  ...
  # —— Phase 2b-1 新增 ——
  pyramid_max_levels: 3
  pyramid_top_k: 10
  pyramid_min_energy_ratio: 0.1
  pyramid_layer_decay_base: 0.7        # source 0.7^level，TagMemoEngine.js:173
  activation_multiplier_min: 0.5       # config.activationMultiplier[0]
  activation_multiplier_max: 1.5       # config.activationMultiplier[1]
  # entropy_penalty 系数（公式分母 1 + entropy*0.5）已硬编码 0.5 在源里；保留硬编码或暴露为旋钮，brainstorm 时定
```

`coreBoostRange / coreTags / langPenalty*` 留 Phase 2b-2。`dynamic_boost_factor_strategy` 枚举值是否新增 `"pyramid"` brainstorm 决定。

---

## 11. 引用追踪

- ResidualPyramid 类源：ResidualPyramid.js:7-395（394 行总计）
- caller 调用：TagMemoEngine.js:7（require）、L17（声明）、L38-40（实例化）、L76-77（调用）、L86-91（公式）、L96（coreMetric）、L102（debug log）、L130-134（levels 遍历）、L177（adjustedWeight 计算）
- 调参文档：TAGMEMO_TUNING_GUIDE.md L37-44（activationMultiplier）、L45-51（dynamicBoostRange）、L53-59（coreBoostRange）
