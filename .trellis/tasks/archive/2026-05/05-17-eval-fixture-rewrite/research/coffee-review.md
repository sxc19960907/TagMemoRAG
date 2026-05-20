# coffee.jsonl Review (Phase A)

> Generated 2026-05-17. Source: `coffee-proposals.jsonl`.
> Workflow: AI suggestion (this draft) → 人工 review fills the **人工决定** block per query.
> All AI judgments are based on `tests/fixtures/coffee_machine.md` content (53 lines, full read) and 4 product_manuals fixtures.

## Calibration rules (apply consistently across queries)

- `relevant`: chunk content directly answers the query OR is a structurally co-located answer (e.g., the diagnostic step that the chapter sends you to). Adding more relevant chunks lets a real-embedder score correctly when its top-K spreads across multiple legitimately-correct headers.
- `not_relevant`: cross-product manuals (washer/dishwasher/AC/refrigerator) or coffee chunks that don't address the query topic.
- `borderline`: weak topical link (e.g., "水箱" appears in passing). Default → leave out of `relevant`; only add if user judges the chunk should count.
- All cross-product `*.md` chunks under `product_manuals/*` are mechanical not_relevant — never include unless the query explicitly cross-references them.
- 父标题块（如 `## 操作` / `## 维护与清洁`）通常 not_relevant：它们是空的章节头，下属子标题才是答案。

---

## 1. coffee-steam-weak — "蒸汽很小怎么办"

**当前 relevant** (2):
- coffee_machine.md / 蒸汽功能 / contains=["蒸汽很小", "喷嘴"]
- coffee_machine.md / 喷嘴清洗 / contains=["喷嘴堵塞", "蒸汽变小"]

**AI 建议**：

| Source | Chunk | Suggestion | 理由 |
|---|---|---|---|
| h#2 | coffee_machine.md / 蒸汽功能 | **relevant** (已在 relevant) | "若蒸汽很小，先检查喷嘴" — 直接答案 |
| sf#4 | coffee_machine.md / 喷嘴清洗 | **relevant** (已在 relevant) | "喷嘴堵塞会造成蒸汽变小" — 直接答案 |
| sf#7 | coffee_machine.md / E01 不出咖啡 | not_relevant | E01 是水路异常，不是蒸汽 |
| h#8 | coffee_machine.md / 除垢 | borderline → 不加 | "水垢会影响蒸汽压力" 间接相关，但水垢不是"蒸汽很小"的首因 |
| (新) | coffee_machine.md / E05 蒸汽异常 | **relevant 新增** | E05 = 蒸汽压力不足或喷嘴堵塞，处理步骤"清洗喷嘴、补水"完全契合 query |
| h#3, sf#3, sf#6 | 制作咖啡 / WM8 / 操作 | not_relevant | 父标题或跨产品 |
| 其他全部跨产品 | washer / dishwasher / AC / refrigerator | not_relevant | 不同产品 |

**AI 推荐 `relevant`**: 蒸汽功能, 喷嘴清洗, **E05 蒸汽异常** ← 新加 1 条
**text_contains 选择**: E05 蒸汽异常 → `["E05", "蒸汽压力不足"]` 或 `["清洗喷嘴", "补水"]`

**人工决定**：
<!-- ☐ 接受 AI 推荐 / ☐ 修改 / ☐ 标 dropped: 原因 -->

---

## 2. coffee-e05 — "E05 蒸汽异常怎么处理"

**当前 relevant** (1):
- coffee_machine.md / E05 蒸汽异常 / contains=["清洗喷嘴", "补水"]

**AI 建议**：

| Source | Chunk | Suggestion | 理由 |
|---|---|---|---|
| h#1, sf#1 | coffee_machine.md / E05 蒸汽异常 | **relevant** (已在) | 直接答案章节 |
| h#3, sf#3 | coffee_machine.md / 喷嘴清洗 | **relevant 新增** | E05 处理步骤明示"清洗喷嘴" — 操作细节就在该章节 |
| h#4 | coffee_machine.md / 蒸汽功能 | **relevant 新增** | "蒸汽很小先检查喷嘴是否堵塞" 是 E05 的诊断起点 |
| h#7, sf#7 | coffee_machine.md / E01 不出咖啡 | not_relevant | 不同故障 |
| h#5 | coffee_machine.md / 产品介绍 | not_relevant | 营销文案 |
| h#6, sf#6 | coffee_machine.md / 制作咖啡, 操作 | not_relevant | 与故障处理无关 |
| h#8 | coffee_machine.md / 除垢 | borderline → 不加 | 水垢虽影响蒸汽压力，但 E05 处理步骤已经包含清洗喷嘴+补水，除垢是 long-term 维护，不是 E05 应急 |
| 其他跨产品 | — | not_relevant | — |

**AI 推荐 `relevant`**: E05 蒸汽异常, **喷嘴清洗** ← 新, **蒸汽功能** ← 新
**text_contains 选择**: 喷嘴清洗 → `["喷嘴堵塞"]`；蒸汽功能 → `["先检查喷嘴是否堵塞"]`

**人工决定**：
<!-- ☐ 接受 AI 推荐 / ☐ 修改 / ☐ 标 dropped: 原因 -->

---

## 3. coffee-water-tank — "缺水导致出水量不足怎么办"

**当前 relevant** (1):
- coffee_machine.md / 水箱安装 / contains=["缺水", "出水量不足"]

**AI 建议**：

| Source | Chunk | Suggestion | 理由 |
|---|---|---|---|
| h#1 | coffee_machine.md / 水箱安装 | **relevant** (已在) | 直接答案："缺水会导致出水量不足" |
| sf#1 | coffee_machine.md / E01 不出咖啡 | **relevant 新增** | "检查水箱、泵和冲煮单元" — 缺水导致 E01 |
| sf#5 | coffee_machine.md / 制作咖啡 | borderline → 不加 | 仅一句"检查水路"，不直接谈缺水后果 |
| h#8, sf#8 | 除垢 / E05 蒸汽异常 | not_relevant | 与缺水无直接关系 |
| sf#3 | 喷嘴清洗 | not_relevant | 不同问题 |
| sf#6, sf#9 | 制作咖啡的父级 / 操作 | not_relevant | 父标题 |
| 跨产品所有 | — | not_relevant | 不同产品 |

**AI 推荐 `relevant`**: 水箱安装, **E01 不出咖啡** ← 新
**text_contains 选择**: E01 不出咖啡 → `["水箱"]` 或 `["E01", "水箱"]`

**人工决定**：
<!-- ☐ 接受 AI 推荐 / ☐ 修改 / ☐ 标 dropped: 原因 -->

---

## 4. coffee-manual-id-metadata — "缺水 出水量不足 水箱安装"

**当前 relevant** (1):
- coffee_machine.md / 水箱安装 / contains=[]  ← 注意空 text_contains

**AI 建议**：

> Query 形式（关键词列表）+ id `manual-id-metadata` + 空 `text_contains` ⇒ 这条是测 metadata/keyword 命中的 case，不是测语义召回。

| Source | Chunk | Suggestion | 理由 |
|---|---|---|---|
| h#1 | coffee_machine.md / 水箱安装 | **relevant** (已在) | 三个关键词都命中 |
| h#7, sf#1 | coffee_machine.md / E01 不出咖啡 | borderline → 不加 | 仅"水箱"命中，"缺水"+"出水量不足"未直接出现 |
| 其他 | — | not_relevant | — |

**AI 推荐 `relevant`**: 水箱安装 (保持单一)
**text_contains 选择**: 加 `["缺水", "出水量不足"]` 让 case 更可观测（不影响 schema）

**人工决定**：
<!-- ☐ 接受 AI 推荐 / ☐ 修改 / ☐ 标 dropped: 原因 -->

---

## 5. coffee-maintenance-tag-synonym — "喷嘴堵塞 奶泡不足 怎么清洗"

**当前 relevant** (2):
- coffee_machine.md / 喷嘴清洗 / contains=["喷嘴堵塞", "奶泡不足"]
- coffee_machine.md / 除垢 / contains=["水垢", "蒸汽压力"]

**AI 建议**：

| Source | Chunk | Suggestion | 理由 |
|---|---|---|---|
| h#1, sf#1 | coffee_machine.md / 喷嘴清洗 | **relevant** (已在) | 直接答案 |
| h#2 | coffee_machine.md / E05 蒸汽异常 | **relevant 新增** | 蒸汽压力不足或喷嘴堵塞，处理含清洗喷嘴 |
| h#3 | coffee_machine.md / 蒸汽功能 | borderline → 加 | "先检查喷嘴是否堵塞" 与 query 同主题 |
| (已在) | coffee_machine.md / 除垢 | **relevant** (已在) | 水垢影响蒸汽，间接清洗议题 |
| h#5 | coffee_machine.md / 电源连接 | not_relevant | 与喷嘴 / 奶泡无关 |
| h#4 | coffee_machine.md / 产品介绍 | not_relevant | 营销文案 |
| h#10 | coffee_machine.md / 水箱安装 | not_relevant | 不同问题 |
| sf#2 | coffee_machine.md / 安装 | not_relevant | 父标题 |
| sf#9 | coffee_machine.md / 热水功能 | not_relevant | 不同功能 |
| 跨产品 | — | not_relevant | — |

**AI 推荐 `relevant`**: 喷嘴清洗, 除垢, **E05 蒸汽异常** ← 新, **蒸汽功能** ← 新
**text_contains 选择**: E05 → `["喷嘴堵塞"]`；蒸汽功能 → `["先检查喷嘴是否堵塞"]`

**人工决定**：
<!-- ☐ 接受 AI 推荐 / ☐ 修改 / ☐ 标 dropped: 原因 -->

---

## 6. coffee-e01-water-path — "E01 不出咖啡检查什么"

**当前 relevant** (1):
- coffee_machine.md / E01 不出咖啡 / contains=["水箱", "泵", "冲煮单元"]

**AI 建议**：

| Source | Chunk | Suggestion | 理由 |
|---|---|---|---|
| h#1, sf#1 | coffee_machine.md / E01 不出咖啡 | **relevant** (已在) | 直接答案 |
| h#2 | coffee_machine.md / 制作咖啡 | **relevant 新增** | "若不出咖啡，请检查研磨器、粉仓和水路" — 同问题不同章节 |
| h#7 | coffee_machine.md / 水箱安装 | **relevant 新增** | E01 检查项首位是水箱 |
| h#6 | coffee_machine.md / 蒸汽功能 | not_relevant | 蒸汽问题不影响 E01 |
| sf#2 | coffee_machine.md / E05 蒸汽异常 | not_relevant | 不同故障码 |
| sf#6 | coffee_machine.md / 热水功能 | not_relevant | — |
| 跨产品 | washer/dishwasher/refrigerator | not_relevant | 不同产品 |

**AI 推荐 `relevant`**: E01 不出咖啡, **制作咖啡** ← 新, **水箱安装** ← 新
**text_contains 选择**: 制作咖啡 → `["若不出咖啡", "研磨器"]`；水箱安装 → `["水箱", "缺水"]`

**人工决定**：
<!-- ☐ 接受 AI 推荐 / ☐ 修改 / ☐ 标 dropped: 原因 -->

---

## 7. coffee-hard-pressure-case — "蒸汽压力不足 可能是喷嘴堵塞还是水垢"

**当前 relevant** (3):
- coffee_machine.md / E05 蒸汽异常 / contains=["蒸汽压力不足", "喷嘴堵塞"]
- coffee_machine.md / 喷嘴清洗 / contains=["蒸汽变小"]
- coffee_machine.md / 除垢 / contains=["蒸汽压力"]

**AI 建议**：

| Source | Chunk | Suggestion | 理由 |
|---|---|---|---|
| h#1 | coffee_machine.md / E05 蒸汽异常 | **relevant** (已在) | 直接答案 |
| h#3, sf#3 | coffee_machine.md / 喷嘴清洗 | **relevant** (已在) | 喷嘴堵塞分支 |
| h#6 | coffee_machine.md / 除垢 | **relevant** (已在) | 水垢分支 |
| h#2 | coffee_machine.md / 蒸汽功能 | **relevant 新增** | "若蒸汽很小，先检查喷嘴是否堵塞" 直接讲 query 的两个候选成因之一 |
| h#4, h#7 | coffee_machine.md / 产品介绍, 电源连接 | not_relevant | 不相关 |
| h#8, sf#8 | coffee_machine.md / 制作咖啡, E01 | not_relevant | 不同问题 |
| h#9 | coffee_machine.md / 水箱安装 | not_relevant | 缺水非该 query 议题 |
| 跨产品 | — | not_relevant | — |

**AI 推荐 `relevant`**: E05 蒸汽异常, 喷嘴清洗, 除垢, **蒸汽功能** ← 新
**text_contains 选择**: 蒸汽功能 → `["先检查喷嘴是否堵塞"]`

**人工决定**：
<!-- ☐ 接受 AI 推荐 / ☐ 修改 / ☐ 标 dropped: 原因 -->

---

## 全局 AI 评估

| Query | 当前 relevant 数 | AI 推荐 relevant 数 | 净增 | 推荐 dropped? |
|---|---|---|---|---|
| coffee-steam-weak | 2 | 3 | +1 | 否 |
| coffee-e05 | 1 | 3 | +2 | 否 |
| coffee-water-tank | 1 | 2 | +1 | 否 |
| coffee-manual-id-metadata | 1 | 1 | 0 | 否 |
| coffee-maintenance-tag-synonym | 2 | 4 | +2 | 否 |
| coffee-e01-water-path | 1 | 3 | +2 | 否 |
| coffee-hard-pressure-case | 3 | 4 | +1 | 否 |
| **总计** | 11 | 20 | **+9** | 0 |

**全局观察**：
- AI 没建议 drop 任何 query — 7 个 query 在 manual 里都有可靠答案。
- 净增 9 个 relevant chunk，主要集中在故障码 (E01/E05) 跨章节互引（fixture 当年只标了"主答案章节"，AI 候选清单暴露了"诊断起点章节"也是合理答案）。
- 没有候选需要走 `--extra-candidates` 兜底——双 embedder 并集已经覆盖所有合理答案。这是 D6.f 没被触发的一种良性状态。

## 你的 review 流程建议

1. 逐 query 看上面的 AI 建议表，在每个 query 末尾的 `**人工决定**` 处填：
   - **接受**：直接写 "Accept AI" 即可。
   - **修改**：列出你要加 / 减 / 改的 chunk + 理由。
   - **dropped**：query 完全不该测（manual 不支持），写 "DROP: 原因"。
2. review 完后告诉我哪些 query 需要改 `text_contains` 的具体短语（如果你觉得 AI 选的不准）。
3. 我据此更新 `coffee.jsonl` + 重 capture baseline + 跑验收。

预估你的 review 时间：每 query 1-2 分钟，7 query ≈ 10-15 分钟。
