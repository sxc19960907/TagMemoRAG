# Source: V6 applyTagBoost 三个外围调制器逐行解析

> 抓取 `lioensky/VCPToolBox` 主分支 `TagMemoEngine.js` 中 4 段相关代码：
> [3.5] 公式里的 `dynamicCoreBoostFactor`（已在 Phase 2b-1 公式接通时跳过）
> [4] 候选收集时的 `coreBoost / langPenalty`
> [4.6] 核心 tag 补全（`coreTagSet` 缺失补 DB 召回）
> [4.7] 幽灵 tag 注入（caller 提供向量，绕过 DB）

源 URL：https://github.com/lioensky/VCPToolBox/blob/main/TagMemoEngine.js

---

## 1. caller 入参（TagMemoEngine.js:61）

```js
applyTagBoost(vector, baseTagBoost, coreTags = [], coreBoostFactor = 1.33)
```

`coreTags` 是个鸭子类型数组（line 110-128）：
- `string` 元素 ⇒ 普通 core tag 名（小写存进 `coreTagSet`）
- `{name, vector, isCore: true}` ⇒ hard ghost（带向量，强制 core 加权）
- `{name, vector, isCore: false}` ⇒ soft ghost（带向量，普通注入）

`coreBoostFactor=1.33` 形参实际**没用**（被 dynamicCoreBoostFactor 覆盖）。

## 2. dynamicCoreBoostFactor（TagMemoEngine.js:96-98）

```js
const coreMetric = (logicDepth * 0.5) + ((1 - features.coverage) * 0.5);
const coreRange = config.coreBoostRange || [1.20, 1.40];
const dynamicCoreBoostFactor = coreRange[0] + (coreMetric * (coreRange[1] - coreRange[0]));
```

物理含义：query 越聚焦（logicDepth 高）或 query 越新颖（coverage 低）⇒ core tag 越被放大。
范围 `[1.20, 1.40]`，是 individualRelevance 之外的"基础聚光灯"系数。

## 3. coreBoost + langPenalty + layerDecay（TagMemoEngine.js:140-180）

每个 pyramid level 的 tag 在加权时都会过这 3 个调制器：

```js
const tagName = t.name ? t.name.toLowerCase() : '';
const isCore = tagName && coreTagSet.has(tagName);
const individualRelevance = t.similarity || 0.5;
const coreBoost = isCore
    ? dynamicCoreBoostFactor * (0.95 + individualRelevance * 0.1)
    : 1.0;

let langPenalty = 1.0;
if (this.config.langConfidenceEnabled) {
    const tName = t.name || '';
    const isTechnicalNoise =
        !/[一-龥]/.test(tName)               // 不含中文
        && /^[A-Za-z0-9\-_.\s]+$/.test(tName)        // 纯英数符号
        && tName.length > 3;                         // 长度 > 3
    const isTechnicalWorld = queryWorld !== 'Unknown'
        && /^[A-Za-z0-9\-_.]+$/.test(queryWorld);
    if (isTechnicalNoise && !isTechnicalWorld) {
        const isSocialWorld = /Politics|Society|History|Economics|Culture/i.test(queryWorld);
        const comp = config.languageCompensator || {};
        const basePenalty = queryWorld === 'Unknown'
            ? (comp.penaltyUnknown ?? this.config.langPenaltyUnknown)
            : (comp.penaltyCrossDomain ?? this.config.langPenaltyCrossDomain);
        langPenalty = isSocialWorld ? Math.sqrt(basePenalty) : basePenalty;
    }
}

const layerDecay = Math.pow(0.7, level.level);   // Phase 2b-1 已实装

allTags.push({
    ...t,
    adjustedWeight: (t.contribution || t.weight || 0) * layerDecay * langPenalty * coreBoost,
    isCore,
});
```

**关键观察**：
- `queryWorld = epaResult.dominantAxes[0]?.label || 'Unknown'`（line 73）— 来自 EPA basis labels。
- TagMemoRAG 的 EPA basis labels 是 `axis-{idx}`（cold-start）或最相似 tag 名（real-pca，`_labels_for_axes` 选 max sim 的原始 tag name）。
- `isTechnicalWorld` 用正则 `/^[A-Za-z0-9\-_.]+$/` 测纯英数符号 — 我们的 real-pca label 是 tag name（fixture 都是英文 `cleaning/cooling/...`），会触发"技术世界"识别。**这意味着 hashing fixture 上 langPenalty 大概率不触发**（query world 也是技术世界），符合期望。
- 中文/英文混合 query 在 cold-start basis 下 `queryWorld='axis-0'` 也匹配技术正则，langPenalty 同样不触发。
- 默认 `langPenaltyUnknown=0.4` / `langPenaltyCrossDomain=0.3`（业内常见，需在 config 里给出默认值）。

## 4. core tag 补全（TagMemoEngine.js:312-342）

```js
if (coreTagSet.size > 0) {
    const missingCoreTags = Array.from(coreTagSet).filter(ct =>
        !allTags.some(at => at.name && at.name.toLowerCase() === ct)
    );
    if (missingCoreTags.length > 0) {
        const placeholders = missingCoreTags.map(() => '?').join(',');
        const rows = this.db.prepare(`SELECT id, name, vector FROM tags WHERE name IN (${placeholders})`).all(...missingCoreTags);
        const maxBaseWeight = allTags.length > 0
            ? Math.max(...allTags.map(t => t.adjustedWeight / 1.33))
            : 1.0;
        rows.forEach(row => {
            if (!seenTagIds.has(row.id)) {
                allTags.push({
                    id: row.id, name: row.name,
                    adjustedWeight: maxBaseWeight * dynamicCoreBoostFactor,
                    isCore: true, isVirtual: true,
                });
                seenTagIds.add(row.id);
            }
        });
    }
}
```

caller 指定的 core tag 如果没出现在 pyramid+spike 候选里，**强制从 DB 召回并以最大权重注入**。`isVirtual: true` 标记，仅参与 context vector，不影响调试统计。

注意：源里这段是 `tags.name`（无 kb_name 字段），TagMemoRAG 的 schema 是 `(kb_name, name) UNIQUE` ⇒ 移植时按 kb_name 限定。

## 5. ghost tag 注入（TagMemoEngine.js:344-372）

```js
let ghostIdCounter = -1;
const ghostVectorMap = new Map();
const maxBaseWeight = allTags.length > 0
    ? Math.max(...allTags.map(t => t.adjustedWeight / 1.33))
    : 1.0;

const injectGhosts = (ghosts, isCore) => {
    ghosts.forEach(ghost => {
        const gid = ghostIdCounter--;             // 负数 id，避免与 DB 冲突
        allTags.push({
            id: gid, name: ghost.name,
            adjustedWeight: maxBaseWeight * (isCore ? dynamicCoreBoostFactor : 1.0),
            isCore, isVirtual: true,
        });
        ghostVectorMap.set(gid, {
            id: gid, name: ghost.name,
            vector: ghost.vector,                 // Float32Array
        });
        seenTagIds.add(gid);
    });
};
injectGhosts(hardGhostObjects, true);
injectGhosts(softGhostObjects, false);
```

后续在 [5] 批量取向量时把 `ghostVectorMap` 合并进 `tagDataMap`（line 384-386），让幽灵 tag 走完整 dedup + context vector pipeline。

## 6. 总结：4 个调制器接到哪里

源代码里这 4 段全部在 **[4] candidate 收集 → [4.6] core 补全 → [4.7] ghost 注入 → [5] 取向量** 这一顺序里串行。在 TagMemoRAG 现有 `apply_tag_boost`（src/tagmemorag/wave_tag_spike.py:391-481）里，对应位置：

```python
# 当前 apply_tag_boost 的关键 anchor（Phase 2b-1 末态）：
# (1) tag_rows = _load_kb_tag_vectors(...)
# (2) pyramid_result = ResidualPyramid(...).analyze(query_vec)  if strategy=pyramid
# (3) seeds_with_sim = pyramid candidates with layer_decay  OR  _select_seeds top-K cosine
# (4) spike_result = propagate(seed_weights, matrix, ...)
# (5) merge seeds + emergent → candidates
# (6) deduped = _semantic_dedup(candidates, ...)
# (7) context = _weighted_context(deduped, dim=...)
# (8) dynamic = _resolve_dynamic_boost(query_vec, settings, pyramid_features=...)
# (9) alpha = clip(base_tag_boost * dynamic, [dyn_min, dyn_max])
# (10) fused = (1-alpha)*query + alpha*context
```

**Phase 2b-2 改动点**：
- 在 (3) 里把 pyramid candidates 收集时，每个 candidate 的 weight 不再是 `contribution * layer_decay`，而是 `contribution * layer_decay * langPenalty * coreBoost`。
- 在 (5) 之后、(6) 之前，加 [4.6] core completion + [4.7] ghost injection 两段。
- core completion / ghost injection 产出 `_TagVecRow`-shaped entry 与现有 candidates 同 schema，不动 dedup / context / fuse 主路径。
- worldview 信号 = `EPAProjector.project(query)["dominantAxes"][0]["label"]`，已在 Phase 0 实现，本任务直接读。
- `dynamicCoreBoostFactor` 在 `_resolve_dynamic_boost(strategy="pyramid")` 同处算，作为副产品 / 函数返回值之一，但不再走 dynamic 出口（dynamic 仍是 effectiveTagBoost 的乘子；core 系数走 candidate adjustedWeight 路径）。

## 7. 与 TagMemoRAG 现状的契合度

| 源依赖 | 现状 | 移植决策 |
|---|---|---|
| `coreTagSet` (string[]) | API SearchRequest 没有 core_tags 字段 | 扩 `SearchFilters` 或 SearchRequest 加 `core_tags: list[str]` |
| `hardGhostObjects` / `softGhostObjects` (含向量) | 没有 | 扩入参 `ghost_tags: list[GhostTagSpec]`；caller 自己 encode 或 pass 向量 |
| `queryWorld` from EPA dominantAxes | ✅ 已实现（`epa_projector.project()["dominantAxes"]`） | 直接用 |
| `langConfidenceEnabled` flag | 没有 | 加 `wave_phase1.lang_penalty_enabled: bool = False`（默认 off，opt-in） |
| `langPenaltyUnknown` / `langPenaltyCrossDomain` | 没有 | 加默认 0.4 / 0.3 字段 |
| `coreBoostRange` | 没有（Phase 2b-1 故意跳过） | 加 `core_boost_min: float = 1.20` / `core_boost_max: float = 1.40` |
| tag DB schema `tags.name UNIQUE` | TagMemoRAG `(kb_name, name)` UNIQUE | core completion 按 kb_name 限定 |
| ghost vector 必须与 query 同维 | TagMemoRAG `model.dim` 全局一致 | `apply_tag_boost` 入口加 dim check + skip-with-reason |

## 8. Python 移植细节注意点

1. **dim 校验**：caller 传 ghost 向量可能 dim 不匹配 ⇒ skip + 计数到 `info.skipped_reason` / metric。
2. **synonym 自动展开**：`tag_governance` 已有 synonym 映射表；core_tags caller 写同义词的话，要不要自动 resolve 到 canonical？**推荐 resolve**（Phase 2b-2 默认行为），避免 caller 关心数据库内部命名。
3. **空字符串 / 重复**：core_tags / ghost_tags 输入要 dedup + 过滤空串。
4. **跨 KB**：搜索是 per-KB 的，core_tags 也按 `state.kb_name` 限定。多 KB 同名 tag 是不同 entity，不要互相污染。
5. **isCore 和 isVirtual 标记**：跟着 candidate 一路传到 `TagBoostInfo` 出口，便于诊断。
6. **maxBaseWeight 基准**：源用 `Math.max(t.adjustedWeight / 1.33)`，1.33 是历史 coreBoostFactor 形参。Python 端用 `max(t.weight) / dynamicCoreBoostFactor` 等价（如果 dynamic 为 0 退化为 1.0）。这样 ghost / core completion 注入的权重和真实 candidates 同一量级，不会过度主导。

## 9. 默认值与产线策略

源默认：
- `coreBoostRange = [1.20, 1.40]`
- `langPenaltyUnknown = 0.4`（query 世界识别不出时的默认惩罚）
- `langPenaltyCrossDomain = 0.3`（query 是非技术世界，但 tag 是英文技术词）
- `langConfidenceEnabled` 在源里默认 true。

**Phase 2b-2 产线策略**（推荐）：
- 所有外围调制器**默认 off**（lang_penalty_enabled=false，core_tags / ghost_tags 入参默认空）。
- 仅当 caller 显式传 core_tags / ghost_tags / 显式开 lang_penalty_enabled 时才生效。
- 默认 strategy=constant 时，本任务**所有改动等价无操作**（不动 R5）。
- strategy=pyramid + caller 不传 core/ghost + lang_penalty_enabled=false ⇒ Phase 2b-1 完全等价。
