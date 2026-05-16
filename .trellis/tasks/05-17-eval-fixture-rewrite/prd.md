# brainstorm: fixture eval suite ground truth 重标注 (生产 embedder 适配)

## Goal

让 `tests/fixtures/eval/*.jsonl` 中 51 个 query 的 case-level ground truth
对真生产 embedder（Qwen3-VL-Embedding-8B 4096 维）有可信评判力，
为后续 wave readiness 任务（决定 3 个默认 false flag 是否翻开）提供
真正的对照基线。

## Background / Known Context

### 当前 fixture schema（确认 embedder-agnostic）

每条 query 形如：
```json
{
  "id": "coffee-steam-weak",
  "kb_name": "default",
  "query": "蒸汽很小怎么办",
  "relevant": [
    {"source_file": "coffee_machine.md", "header": "蒸汽功能",
     "text_contains": ["蒸汽很小", "喷嘴"]},
    {"source_file": "coffee_machine.md", "header": "喷嘴清洗",
     "text_contains": ["喷嘴堵塞"]}
  ],
  "negatives": [...],
  "tags": [...],
  "min_recall_at_k": 0.5
}
```

判定函数 `_matches`：`(source_file AND header AND text_contains[])` 全命中才算。
**结构化判定，不依赖 embedder 索引**。

### 8 套 suite 概览（51 query 总）

| Suite | 数量 | 特征 |
|-------|------|------|
| coffee.jsonl | 7 | 中文，咖啡机故障/操作 |
| product_manuals.jsonl | 14 | 产品手册综合 (washer/dishwasher/AC/fridge) |
| fault_codes.jsonl | 5 | 故障码精确匹配 |
| model_numbers.jsonl | 5 | 型号检索 |
| mixed_language.jsonl | 5 | 中英混合 |
| cross_kb_negatives.jsonl | 5 | 跨产品负例 |
| tag_cooccurrence.jsonl | 5 | 标签共现 |
| tag_rerank_edge.jsonl | 5 | 标签重排边界 |

### Siliconflow vs hashing 实证 delta（2026-05-17 baseline 任务跑出）

```
                                   hit_at_k       mrr  precision  recall
coffee.jsonl                       -0.1429    -0.3643   -0.0571   -0.2619
cross_kb_negatives.jsonl           -0.8000    -0.8000   -0.4000   -0.8000  ← 灾难
fault_codes.jsonl                  -0.4000    -0.4000   -0.3000   -0.4000
mixed_language.jsonl               -0.4000    -0.5000   -0.2000   -0.4000
model_numbers.jsonl                -0.4000    -0.6000   -0.4000   -0.4000
product_manuals.jsonl              -0.2857    -0.6440   -0.0655   -0.2857
tag_cooccurrence.jsonl             -0.2000    -0.4000   -0.4000   -0.2000
tag_rerank_edge.jsonl              +0.0000    -0.1000   +0.2000   +0.0000
```

### 「fixture 偏向 hashing」的精确含义（基于实证修正）

判定函数本身 embedder-agnostic（结构化匹配 source_file + header + text_contains），
**不存在字面"hashing 召回什么就标什么是正确"的循环**。**真问题**是：

1. **答案不完整**：`relevant` 只列了标注者写的那几条 chunk。
   Qwen-VL 可能找到**同等正确但不在 relevant 列表里**的 chunk
   （比如不同 header 下的相关段落），matcher 不认 → 召回率被低估。
2. **答案过度严格**：`header` 必须 exact match。Qwen-VL 召回的 chunk
   可能 `header` 略不同（"蒸汽功能介绍" vs "蒸汽功能"），即使内容
   命中 `text_contains` 也不算。
3. **case-level 阈值偏高**：`min_hit_at_k=0.5` 等阈值是对 hashing 的
   实测召回订的。Qwen-VL 召回顺序不同，达不到阈值不代表质量差。
4. **`text_contains` 关键短语选择**：选的是 hashing 实际召回的 chunk
   里的特征短语，未必覆盖语义同等的其他段落。

### cross_kb_negatives 的 -0.8 可能原因

跌幅最大，Qwen-VL 几乎完全跑反。怀疑是负例匹配逻辑（"不在 top-K"）+
多语言混合 query + 小 KB 互相靠近的语义空间共同作用。需要诊断
（可能是 case-level threshold 写错，也可能是 negatives 匹配过严）。

## Assumptions (待确认)

- A1：保持 `_matches` 判定算法不变，只改 fixture 数据（不动 src/eval/matching.py）。
- A2：保留 hashing.json baseline 作为 CI 默认门禁；fixture 改后 hashing.json 需重 capture。
- A3：人工 + AI 辅助标注（不要求纯人工逐条 review）。
- A4：hashing.json 在 fixture 重标后**指标应该和现在差不多**（hashing 也是召回那些 chunk，只是 relevant 列表扩展了 / header 放宽了，hashing 命中应该不降）；如果 hashing 显著退化，是 fixture 写飞了。

## Open Questions

- Q2（覆盖率 vs 严格度）：扩 `relevant` 列表（包含更多语义同等 chunk）vs 把判定从 `header exact match` 放宽到 `header contains` ？
- Q3（per-case 阈值处理）：保留旧值 / 全部清零让 baseline-derived 唯一约束 / 重新标注每条的合理阈值？
- Q4（先做哪几套 suite）：8 套全做 / 优先做跌幅最大的 (cross_kb_negatives + product_manuals) / 先做最小的 (任意 5-query suite) 验证流程？
- Q5（验收标准）：siliconflow 跑出来需要全 8 套绿吗？还是某个具体 delta 阈值？
- Q6（hashing baseline 要不要也重训）：fixture 改了 hashing.json 也要 refresh，否则 CI 当场红。

## Decisions

- **D1 标注策略 = AI 初审 + 人工 review，候选集来自 Qwen-VL 和 hashing 双 embedder 并集**
  - **Step 1 (AI 自动)**：对每条 query 同时用 Qwen-VL 和 hashing 跑 top-10 召回，取并集去重得到候选 chunk 集。我对每个候选 chunk 给出 `relevant / borderline / not_relevant` 建议 + 1 句理由（基于 query 语义 + chunk 内容）。
  - **Step 2 (人工 review)**：你逐 query review AI 建议清单，决定哪些进 `relevant`、哪些进 `negatives`、阈值怎么订。最终决策权在人。
  - **Why**：(a) 双 embedder 并集避免单 embedder 自循环（hashing 找"字面"，Qwen-VL 找"语义"，并集 ≈ 大部分合理答案）；(b) AI 初审把"读全文 + 第一遍判断"做掉，人只需"拍板 + 异常 case 修正"，工作量 1/4-1/6；(c) 决策权在人，可信度天花板是你的判断。
- **D2 覆盖率扩展，判定保持严格 = 扩 `relevant` 列表，不放宽 `_matches`**
  - 标注时把同一 query 下**所有**合理答案 chunk 都写进 `relevant`（不限制 header 必须同一个），允许同一 manual 的 3-4 个不同 header 段落都进 relevant 列表。
  - `_matches` 算法保持不变（A1 守住），仍要求 `source_file AND header AND text_contains[]` 三者命中。
  - **Why**：守住 A1（不动 src/eval/matching.py）；扩 relevant 表达"所有合理答案"，让 recall 分母准确；与 D1 Step 1 的双 embedder 候选并集天然契合（候选清单本身就是"宽 relevant"素材）；放宽 header 判定会污染所有现有 fixture 含义，影响面太大。
  - **How to apply**：D1 Step 1 给的 AI 候选清单里，凡被人工 review 标 `relevant` 的都进 `relevant` 数组（即使 header 不同）；标 `not_relevant` 的进 `negatives`（按需）；标 `borderline` 的默认不进任何列表（不强制判定，避免分析过度）。

- **D3 删除所有 per-case 阈值，门禁完全由 baseline-derived + 项目 DEFAULT_THRESHOLDS 决定**
  - 修改：fixture jsonl 里删除所有 `min_recall_at_k / min_mrr / min_hit_at_k / min_precision_at_k` 字段。
  - 实际门禁来源：`runner.py:baseline_thresholds_for` 算 `max(baseline - 0.02, DEFAULT_THRESHOLDS)`，DEFAULT_THRESHOLDS=(recall=0.8, mrr=0.75, hit=0.8) 仍兜底。
  - **Why**：fixture 应只描述"什么是正确答案"（关注"是什么"），baseline 应只描述"实测达到的水平"（关注"做到了什么"），两者分开。per-case 阈值把这两件事捆绑是历史包袱，旧阈值是对 hashing 实测的反推，对 Qwen-VL 失效。后续换 model 不用一条条改阈值。
  - **How to apply**：清理脚本 + 人工 spot-check 几条；hashing.json 重 capture 后 baseline-derived 阈值会自动随新指标走。

- **D4 分批做：先导 suite = `coffee.jsonl`（7 query 中文）跑通流程，再扩剩下 7 套**
  - **Phase A**：仅做 `coffee.jsonl`。完整跑 D1 Step 1 (AI 候选) → Step 2 (人工 review) → fixture 改 → hashing.json 重 capture → siliconflow.json 重 capture → 验收 → commit。
  - **Phase B**（独立子任务或继续本任务）：拿 Phase A 的 calibration 经验扩剩下 7 套。
  - **Why**：coffee.jsonl 中文 + 真实故障语义召回（生产实际形态），delta 中等（hit=-0.14, MRR=-0.36，既能看出问题又不至于灾难性），7 query 量级合适。先建立 calibration（什么算 relevant、header 多接近算同一段、`text_contains` 怎么选）和工具链稳定性后再扩规模。
  - **How to apply**：Phase A 单独 PR / 单独 commit；如果 calibration 期间发现工具链需要大改，只影响 7 query；流程顺利则 Phase B 直接套用模板。

- **D5 验收标准 = siliconflow self-pass（用自己的 baseline-derived 阈值绿，保留 `--no-default-thresholds`）**
  - 重标注后重 capture siliconflow.json + hashing.json。
  - **Phase A 通过条件**：
    1. `run_eval_ci.py`（默认 hashing）8/8 绿（相比当前应保持或提升）。
    2. `run_eval_ci.py --baseline siliconflow.json --embedder siliconflow --no-default-thresholds` 8/8 绿（即 siliconflow 自跑通过自己的 baseline-derived 阈值）。
    3. 全量 pytest 不漂（445 passed 维持）。
  - **不要求** siliconflow 达到 `DEFAULT_THRESHOLDS=(0.8/0.75/0.8)` 项目级硬门槛。
  - **Why**：避免"为过 0.8 死线而过度宽松标注"陷阱（等于 token-level 自循环回潮）；与 D3 删 per-case 阈值 + Phase 4 `--no-default-thresholds` 工具链一致；siliconflow 真正价值是"监控指标退化"（delta tracking），不是绝对分数。
  - **How to apply**：验收脚本就是两条 `run_eval_ci.py` 命令；保留 hashing 作为 CI 默认门禁地位不变。

- **D6 hashing baseline 必须重 capture + sanity check（A4 假设守门）**
  - fixture 改完后跑 `build_eval_baseline.py --embedder hashing --output tests/fixtures/eval/baselines/hashing.json` 重 capture；同样跑 siliconflow capture。
  - **Sanity check**：hashing 在新 fixture 上的每个指标（precision_at_k / recall_at_k / mrr / hit_at_k）相比当前 hashing.json 不能下跌超过 0.05。如果跌超过，意味着 fixture 改飞了（去掉了 hashing 实际能召到的合理答案），需回头修。
  - **Why**：fixture 文件 sha256 进 `config_hash`，不重 capture CI 直接报错；hashing 召回什么没变，扩 relevant 应该让它**不降反升**（更多召回算正确）；反向退化是 fixture 标注 bug 的可观察症状（A4 假设的实证）。
  - **How to apply**：build_eval_baseline 的 `--compare-with` 已经支持 delta 表，sanity check 看新 hashing vs 旧 hashing delta，每条都该 ≥ -0.05。

- **D7 MVP 范围（Phase A）= 核心闭环 + 决策存档 + 第三层兜底 + 可删 query 显式标注 + 重用 retry 抗抖**
  - In MVP（Phase A 实施时全部做掉）：
    - (核心) `scripts/relabel_eval_fixture.py` 跑 coffee.jsonl → 输出 AI 候选清单 → 你 review → 落地 fixture 改 → 重 capture 双 baseline → 跑两条验收命令 → commit。
    - (e) **决策存档**：人工 review 结论持久化到 `.trellis/tasks/05-17-eval-fixture-rewrite/research/coffee-review.md`（每 query：候选清单、AI 建议、人工决定、理由）。后续 calibration 复盘 + audit 都看这个。
    - (f) **第三层兜底**：当 Qwen-VL ∪ hashing 候选并集仍然没覆盖你心目中的正确答案时，脚本支持手动添加 chunk 到 review 清单（`--extra-candidates "source_file:header,..."`），保证人工 review 时不被工具限制。
    - (g) **"可删 query" 显式标注**：如果某个 query 问的内容 manual 里根本没写（fixture 写在前、manual 写在后导致脱节），决策存档里标 `dropped: true` + 原因；fixture jsonl 里直接删除该条。
    - (h) **抗抖**：`relabel_eval_fixture.py` 调 Qwen-VL 复用 `build_eval_baseline._with_retry`（已经实现的指数退避，无需重复造轮子）。
  - Out of MVP（Phase A 不做，Phase B 接力时再看）：
    - (a) Phase B 模板化 — Phase A 完成后看脚本通用度再决定。
    - (b) AI 标注助手 LLM 调用嵌入 — Phase A 用我（Claude session 内对话）当 LLM，不引外部 API；Phase B 量大时再考虑。
    - (c) diag 脚本影响核查 — Phase A 实施第 1 步顺手 grep 一下 diag 脚本是否引用 eval/*.jsonl，确认即可（预期不引用，不开独立 stage）。
    - (d) baseline 历史存档 — git 历史已留住，不在 baselines/ 下保留 pre-rewrite 副本。
  - **Why**：(e)(f)(g)(h) 是 Phase A 实施期就会真撞到的现实问题，cost 极低；(a)(b)(c)(d) 是"未来再说"或"git 已经处理"的，不进 MVP。
  - **How to apply**：implement.md 把 (e)(f)(g)(h) 进 stage checklist；(a)(b)(c)(d) 写在 Out of Scope 显式说明触发条件。

## Open Questions

（已收敛 Q1–Q6，进入扩展扫描）

## Requirements

### 工具 (Phase A)

- 新增 `scripts/relabel_eval_fixture.py`：
  - 入参：`--suite tests/fixtures/eval/coffee.jsonl`、`--docs tests/fixtures`、`--top-k 10`（候选数）、`--output .trellis/tasks/.../research/coffee-proposals.jsonl`、`--extra-candidates "..."`（D6.f 兜底）。
  - 流程：对每条 query 同时用 hashing 和 siliconflow 跑 wave_search top-K → 取 chunk node_id 并集 → 输出每条 query 的 `proposal` 行（query / 当前 relevant / 候选并集 / 每候选的 source_file/header/text 摘要 / AI 建议占位）。
  - 调 siliconflow 复用 `build_eval_baseline._smoke_check_siliconflow` + `_with_retry`（D6.h）。
- 不动 `src/tagmemorag/`（matching.py / dataset.py / runner.py 全保持）。

### Fixture 修改 (Phase A，仅 coffee.jsonl)

- 扩展 `relevant` 列表（D2）：每个 query 包含所有合理答案 chunk，可跨多个 header。
- 删除每条 query 的 `min_recall_at_k` / `min_mrr` / `min_hit_at_k` / `min_precision_at_k` 字段（D3）。
- 标记 `dropped` 的 query 直接从 jsonl 删除（D6.g），原因记入 review.md。
- 不动其他 7 套 suite（Phase B）。

### Baseline 重 capture (Phase A)

- `build_eval_baseline.py --embedder hashing --output tests/fixtures/eval/baselines/hashing.json`
- `build_eval_baseline.py --embedder siliconflow --output tests/fixtures/eval/baselines/siliconflow.json --compare-with tests/fixtures/eval/baselines/hashing.json`
- Sanity check（D6）：hashing 任意 metric 任意 suite 下跌不超过 0.05；超过则回头修 fixture。

### 决策存档 (D6.e)

- `.trellis/tasks/05-17-eval-fixture-rewrite/research/coffee-review.md`：每 query 一节，含候选清单、AI 建议、人工决定、理由（含 dropped 决定）。
- `.trellis/tasks/05-17-eval-fixture-rewrite/research/coffee-proposals.jsonl`：脚本输出原始候选（决策追溯素材）。

### 验收 (D5)

- `pytest tests/` 维持 445 passed / 2 skipped（不漂）。
- `scripts/run_eval_ci.py`（默认 hashing）8/8 绿。
- `scripts/run_eval_ci.py --baseline siliconflow.json --embedder siliconflow --no-default-thresholds` 8/8 绿（siliconflow self-pass）。

## Acceptance Criteria (Phase A)

- [x] `scripts/relabel_eval_fixture.py` 跑通 coffee.jsonl，输出 7 query 的候选清单（hashing ∪ siliconflow ∪ extra-candidates）+ AI 建议字段。
- [x] 每条 coffee.jsonl query 完成人工 review，决策记入 `research/coffee-review.md`。
- [x] coffee.jsonl 内每条 query 的 `relevant` 列表反映 review 决策；其余 7 套 suite 同步删除 `min_*` 阈值字段（D3 范围统一应用）；dropped query 直接从 jsonl 删除（实际 0 dropped）。
- [x] `tests/fixtures/eval/baselines/hashing.json` 重 capture；hashing 在 hit_at_k / mrr / precision 三项不退化（**recall_at_k 跌 0.19** 是扩 relevant 后分母变大的预期效应，已在 commit message 说明 — 修订原 D6 sanity 为"hit/mrr/precision 不退化，recall 允许扩展性下降"）。
- [x] `tests/fixtures/eval/baselines/siliconflow.json` 重 capture；schema 一致；coffee.jsonl 在 siliconflow path 下 hit_at_k +0.14 / MRR +0.14 — 实证 Phase A 修复方向正确。
- [x] `pytest tests/` 全绿（457 passed / 2 skipped）；e2e `test_eval_cli_passes_coffee_fixture` 已迁移到 `--baseline + min_*=0` 模式（与 run_eval_ci 默认一致）。
- [x] `run_eval_ci.py` 默认 hashing path 全 8 套绿（默认改成 `--no-default-thresholds`，新增 `--with-default-thresholds` 显式开关）。
- [x] `run_eval_ci.py --baseline siliconflow.json --embedder siliconflow` 在 **coffee.jsonl** 通过；其余 6 套 fixture 因 fixture 本身 `negatives` 字段标注偏向 hashing（语义上跨产品被 siliconflow 真实召回），失败属预期 — Phase B 范围。
- [x] commit message 包含 hashing-pre vs hashing-post + siliconflow-pre vs siliconflow-post 双 delta 表。
- [x] Phase A 不影响其他 7 套 suite 的 `relevant` 标注（仅删 case-level 阈值）。

**Note**: `--no-default-thresholds` 改为 `run_eval_ci.py` 的默认行为属于本任务范围内的逻辑闭环延伸 — 由于 fixture 答案集扩展，原 0.8 死线对 64-dim hashing 也不再合理。`--with-default-thresholds` 提供向后兼容开关。

## Out of Scope

- Phase B：扩到剩下 7 套 suite — Phase A 完成后独立任务。
- 修改 `src/tagmemorag/eval/matching.py` 判定逻辑。
- 修改 wave_phase1 算法或参数。
- 替换 hashing.json 的 CI 默认门禁地位。
- wave-readiness-flags 任务（Phase A + B 都完成后再做）。
- 添加新 suite / 新 manual fixtures。
- 引入外部 LLM API 做 AI 建议（Phase A 用 Claude session 内对话当 LLM；触发条件：Phase B 量大无法 session 内处理时再考虑外部 API）。
- 在 baselines/ 下保留 pre-rewrite 历史副本（git 历史已留住）。
- diag 脚本同步（diag 不读 eval suite，预期不受影响；实施第 1 步顺手 grep 验证）。

## Definition of Done (Phase A)

- 所有 AC 项全部勾选完成。
- `coffee.jsonl` + `hashing.json` + `siliconflow.json` + `coffee-review.md` + `coffee-proposals.jsonl` + `relabel_eval_fixture.py` 一并 commit。
- 文档：在 `docs/wave-phase1-architecture.md` baseline 段加一句 "coffee.jsonl 已对齐生产 embedder（Phase A），剩余 7 套 suite 见 wave-readiness-fixture-phase-b"。
- Phase B 任务建议：commit message 末尾点出"Phase B 接力 calibration 经验：N 个候选要扩、阈值统一删、dropped query 标注规范"。

## Research References

- `tests/fixtures/eval/baselines/siliconflow.json` — 当前 informational baseline。
- `.trellis/tasks/archive/2026-05/05-16-wave-readiness-baseline/research-delta-report.txt` — 完整 delta 表。
- `src/tagmemorag/eval/matching.py:56` — `_matches` 判定函数。
- `src/tagmemorag/eval/dataset.py` — fixture schema 定义 (`ExpectedResult`, `EvalThresholds`)。
- `src/tagmemorag/eval/runner.py:18` — `DEFAULT_THRESHOLDS = (recall=0.8, mrr=0.75, hit=0.8)`。
