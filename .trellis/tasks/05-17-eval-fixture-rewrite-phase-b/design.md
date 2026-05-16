# Technical Design — Phase B (剩 7 套 suite)

> 父文档：[prd.md](./prd.md)
> Phase A 设计已经验证：[`../05-17-eval-fixture-rewrite/design.md`](../archive/2026-05/05-17-eval-fixture-rewrite/design.md)。Phase B 复用工作流，本文档只点出 Phase A 没覆盖的差异。

## 1. 与 Phase A 的差异

| 维度 | Phase A | Phase B |
|---|---|---|
| Suite 数量 | 1 | 7 |
| Query 数 | 7 | 44 |
| Negatives 处理 | 不显式（coffee.jsonl 没 negatives 字段） | **必须**显式 review + 调整 |
| 验收 | siliconflow coffee 单套绿 | siliconflow 全 8 套绿 |
| 工具 | scripts/relabel_eval_fixture.py 新建 | 重用，不改 |
| Baselines | hashing+siliconflow 重 capture | 同样重 capture |

## 2. Negatives 处理新增逻辑

Fixture 中 `negatives` 字段含义：「这些 chunk 应当不在 top-K 中（top-K 命中即视为 false positive）」。

review 时三种决策：

| 情况 | 处理 |
|---|---|
| siliconflow 召回了某 negative chunk，但语义上其实是合理答案 | 移到 `relevant` |
| siliconflow 召回了某 negative chunk，确实是噪声跨产品干扰 | 保留在 `negatives` |
| Fixture 写得过严（任何相关产品都标 negative） | 删除整个 `negatives` 项或放宽到 `metadata.product_category` 单维约束 |

## 3. 流水线

```
for suite in [cross_kb_negatives, fault_codes, model_numbers,
              tag_cooccurrence, product_manuals, mixed_language,
              tag_rerank_edge]:
    1. relabel → research/{suite}-proposals.jsonl
    2. Claude 起草 → research/{suite}-review.md (含 relevant + negatives 两段)
    3. user review (autonomous mode 默认接受 AI 建议)
    4. 落地 fixture
final:
    5. recapture hashing.json + siliconflow.json
    6. verify (pytest, hashing CI, siliconflow CI)
    7. doc update + commit
```

## 4. 风险点

- **API quota**：44 query × 双 embedder × KB 重建 4 次（hashing 复用，siliconflow 复用 cache 困难）。预估 < Phase A × 7 ≈ 7 倍 API 用量。如 quota 紧 → 改 batch（每套独立 commit），不需要重 capture between suites（baseline 只在最后一次重 capture）。
- **Negatives 灾难性 case**：cross_kb_negatives 是已知 hit=-0.8 的最严重 case，可能需要把多数 negatives 移到 relevant，意味着该 suite 的语义本身要重新定义。如果发现实质性问题 → 单独建子任务讨论，不强行 push。

## 5. Rollback

- 每套 suite 独立可 revert（fixture 文件级别 git revert）。
- 双 baseline 文件 git revert 即可。
- relabel script + run_eval_ci script 不动 → 不会回滚到 Phase A 之前。
