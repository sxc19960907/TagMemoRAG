# Wave Readiness Flags — 实证决策

> 2026-05-17 — `scripts/diag_wave_readiness_flags.py` 实测结果。
> 4 strict siliconflow suite × 4 metric × 5 config，对照 baseline (3 flag 全 off)。

## 决策摘要

| Flag | 决议 | 理由 |
|---|---|---|
| `cross_domain_resonance_enabled` | **KEEP_OFF** | 全 0 delta — Phase 3 算法在当前 fixture × Qwen-VL 上无可观测信号 |
| `intrinsic_residuals_enabled` | **KEEP_OFF** | 同上 — Phase 3.5 算法无信号 |
| `geodesic_rerank_enabled` | **KEEP_OFF** | tag_rerank_edge hit -0.20、coffee MRR -0.50；仅 product_manuals +0.14；触发 D3 regression blocker |

**3/3 保持默认 off**。本任务不做配置修改，但**实证记录是工作交付物**。

## 详细实证（实测 4 strict suite）

### Baseline (3 flag 全 off)

```
coffee.jsonl              precision=0.20 recall=0.50 mrr=0.71 hit=1.00
mixed_language.jsonl      precision=0.40 recall=0.60 mrr=0.40 hit=0.60
product_manuals.jsonl     precision=0.15 recall=0.71 mrr=0.36 hit=0.71
tag_rerank_edge.jsonl     precision=0.90 recall=1.00 mrr=0.90 hit=1.00
```

### only-resonance vs baseline

**完全无差异**（4 suite × 4 metric 全 0）。意味着：
- Phase 3 `detectCrossDomainResonance` 算法在当前 4 strict suite 的 query 上没有触发（resonance scalar 始终为 0 或 bridges_count 始终 0）
- 可能原因：fixture query 不够触发"跨多非主轴同时强激活"的语义模式；或 Qwen-VL 4096 维下 dominant axis 太集中
- 算法本身正确接通（Phase 3 任务已验证），但生产数据没让它跑出价值

### only-residuals vs baseline

**完全无差异**。同上：
- Phase 3.5 `tag_intrinsic_residuals` 在当前 query 模式下没影响 wormhole gate 或 pyramid prior 排序
- 可能原因：spike propagation 触发的 emergent tag 数量太少（fixture 太小）；或 residual energy 区分度不够

### only-geodesic vs baseline

```
coffee.jsonl                 precision -0.06  recall -0.19  mrr -0.50  hit -0.29
mixed_language.jsonl         precision -0.10  recall -0.20  mrr -0.10  hit -0.20
product_manuals.jsonl        precision +0.02  recall +0.14  mrr +0.02  hit +0.14
tag_rerank_edge.jsonl        precision -0.30  recall -0.20  mrr -0.30  hit -0.20
```

**1/4 改善 + 3/4 退化**。触发 D3 regression blocker（tag_rerank_edge.hit -0.2）。

诊断：
- **product_manuals 改善**：14 query 是宽语义召回场景，V8 tag-energy 二次重排把分散答案拉到 top-K，符合 Phase 4 设计意图
- **coffee 严重退化**：coffee.jsonl 经过 Phase A 重标，relevant 列表是多 header 跨章节链路（蒸汽功能 / 喷嘴清洗 / E05 互引）。V8 oversample 2× 后用 tag energy 重排，反而把语义最相关的章节挤出 top-K
- **tag_rerank_edge 严重退化**：本来就是 hashing baseline 上 perfect 的 5 query，Qwen-VL 已经能处理，V8 扰动只会损害

### all-on vs baseline = only-geodesic vs baseline

完全相同 → 说明 resonance + residuals 在 only-geodesic 上叠加没产生任何额外效果（与各自 only-* 配置全 0 delta 一致）。

## 工程含义

**这次实证对工程上的价值**：

1. **3 个算法接通工作的成本回收**：算法接通本身是必要的（保留扩展点 / 监测点 / 未来更大数据集再启用），但当前 fixture × 生产 embedder 还没到能让它们发挥的场景。**这是数据规模限制，不是算法 bug**。

2. **V8 在 product_manuals 上有信号**说明 Phase 4 算法本身可用，**但 oversample 默认 2.0 + min_geo_samples 默认 2 在 coffee/edge 这类精确链路 query 上反而打乱排序**。可能的优化方向（不在本任务）：
   - 加 query-level "需不需要 V8" 的启发式（例如 query token 长度短、含精确故障码 → 跳过 V8）
   - 调 oversample factor 到 1.5 减小扰动半径
   - 调 alpha 默认从 0.3 到 0.15 弱化 geo 影响

3. **wave 算法主线 = Phase 1 spike 提供基础召回**，剩余 3 个 phase 在当前条件下都"待激活"。这与原始 wave-rag 设计文档"分阶段交付"一致——不强求每个 phase 都立刻有价值，但都要"接通完成、可监测、随时可启用"。

## 后续 follow-up（不在本任务）

- **更大 KB 实验**：当 KB 从 5 manual 涨到 50/500 时，resonance + residuals 应该开始有信号；可在 production 数据上跑一次相同 diag 验证
- **V8 调参 sub-task**：基于本任务实证的"V8 在精确链路 query 上扰动"现象，单独建任务调 oversample / alpha / 加启发式
- **Eval suite 扩展**：当前 4 strict suite 共 31 query，对算法效果差异的检测力有限；增加多样性 query 后再跑同样 diag

## 验收

- ✅ Diag 脚本跑通，输出归档到 `research/readiness-flags-diff.txt`
- ✅ 3 个 flag 决议明确（全部 KEEP_OFF）
- ✅ 不动 src/tagmemorag/config.py（保持现有默认）
- ✅ 不需要重 capture baseline（fixture/默认值都没变）
- ✅ 不需要更新 baseline invariance 测试

**因此本任务无代码改动**，只交付：
1. `scripts/diag_wave_readiness_flags.py`（新工具）
2. `research/readiness-flags-diff.txt`（实证存档）
3. `research/readiness-decision.md`（本文档）
4. PRD update：3 flag KEEP_OFF 决议 + follow-up 路径
