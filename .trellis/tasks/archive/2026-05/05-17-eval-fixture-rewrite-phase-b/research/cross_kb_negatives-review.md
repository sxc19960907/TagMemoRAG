# cross_kb_negatives.jsonl Review (Phase B)

> Generated 2026-05-17. Source: `cross_kb_negatives-proposals.jsonl`.

## Critical insight: 不是 fixture bug, 是 stress-test

cross_kb_negatives 用 `metadata.product_category` 字段做 negative 过滤
（"问 fridge 时不应在 top-K 返回 washer 的 chunk"）。这是设计意图，
不是 hashing-self-loop 的副作用。

**5 个 query 的 negatives 都是合理设计**：
- `neg-fridge-not-washer` → washer 不应出现（OK，但实际 siliconflow 召回 AC，AC 不在 negatives 列表里 → 不会触发 negative match）
- `neg-ac-not-fridge` → fridge 不应出现
- `neg-dishwasher-not-washer` → washer 不应出现（注意 fixture 标的实际是 refrigerator，可能写错？需 verify）
- `neg-washer-not-dishwasher` → dishwasher 不应出现
- `neg-fridge-door-not-ac-mode` → air-conditioner 不应出现

实际 siliconflow CI 失败位置（来自 Phase A 末态实测）：

```
neg-washer-not-dishwasher: negative #0 matched at rank 1 (dishwasher/dishwasher_dw6.md)
```

含义：siliconflow 在"洗衣机滚筒清洁"的 query 上把 dishwasher 的某个
chunk 排第 1。这是 **siliconflow 在跨家电场景的真实能力局限**
（语义空间里 washer / dishwasher 太近），不是标注问题。

## 决策（Phase B 范围调整）

**保持 cross_kb_negatives.jsonl 不动**：

- `relevant` 列表已经准确（每个 query 都只有一个真正的答案 chunk）。
- `negatives` 列表用 metadata 过滤是合理的设计意图。
- siliconflow 跑这套 suite 失败，是 **stress test 暴露生产能力**，不应通过改 fixture 来"过线"。

**唯一可能的修订**：检查 `neg-dishwasher-not-washer` 的 negatives 字段
（fixture 写的是 refrigerator？看一下原文件）：

| Query | 当前 negatives.metadata | 应该是 |
|---|---|---|
| neg-fridge-not-washer | `category=washer` | ✅ |
| neg-ac-not-fridge | `category=fridge` | ✅ |
| neg-dishwasher-not-washer | `source_file=refrigerator/...` | **可能写错**（按 query 名应该是 washer category） |
| neg-washer-not-dishwasher | `category=dishwasher` | ✅ |
| neg-fridge-door-not-ac-mode | `category=air-conditioner` | ✅ |

需 spot check `neg-dishwasher-not-washer` 的 fixture 原始字段。

## AC 结论

cross_kb_negatives 是 Phase B 的 **acceptance gap**：
不是 fixture bug，不应"修复"——siliconflow CI 在这套 suite 上 fail
是预期行为。建议：

- 修订 D5 验收：**siliconflow CI 在 7 套（除 cross_kb_negatives）绿**，cross_kb_negatives 作为 stress-test。
- 或：修订 run_eval_ci 增加 `--informational-suites cross_kb_negatives.jsonl` 让该套 suite 失败不算整体 CI fail。

**下一步**：spot check `neg-dishwasher-not-washer` fixture 原文件，看是否需要小修；其余 4 query 不动；继续做 fault_codes.jsonl。
