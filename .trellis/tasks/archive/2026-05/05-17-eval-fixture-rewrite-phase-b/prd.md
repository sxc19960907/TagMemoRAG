# Phase B — 剩 7 套 fixture eval suite 重标注

## Goal

把 Phase A 在 coffee.jsonl 上跑通的双 embedder 候选 + AI 初审 + 人工 review 工作流，复制到剩下 7 套 fixture（cross_kb_negatives / fault_codes / mixed_language / model_numbers / product_manuals / tag_cooccurrence / tag_rerank_edge），让整套 fixture 对生产 embedder（Qwen3-VL-Embedding-8B 4096 维）可信，从而：

1. siliconflow `run_eval_ci.py` 全 8 套绿（不需要 `--no-default-thresholds` 也绿，或至少 case-level negatives 不再误判）。
2. 后续 wave-readiness-flags 任务有可信对照基线。

## Background

Phase A (commit `24adb2e`) 完成：
- coffee.jsonl 7 query 重标，relevant 11→20 chunks。
- 8 套 fixture 全部删 case-level `min_*` 阈值（132 字段）。
- run_eval_ci 默认 `--no-default-thresholds`。
- siliconflow 在 coffee.jsonl 上 hit/MRR +0.14（验证修复方向）。

剩余 7 套问题（实证 from Phase A 跑 siliconflow CI）：
- 4 套 fail 在 **negatives 误匹配**：cross_kb_negatives / fault_codes / model_numbers / tag_cooccurrence
  - siliconflow 真实召回的 chunk 命中了 fixture 标记为"反例"的 source_file，但语义上其实是**合理跨产品答案**，fixture 标记过严。
- 3 套虽然 Phase A 跑过了但相对 hashing 仍弱：mixed_language / product_manuals / tag_rerank_edge
  - relevant 列表 hashing-self-loop 标注偏窄，需扩展。

44 query 待处理 = 51 总 - 7 (coffee 已做)。

## Decisions（沿用 Phase A，无新 brainstorm）

- **D1 标注策略 = 沿用 Phase A**：scripts/relabel_eval_fixture.py 跑双 embedder 候选 → Claude session 内 LLM 给建议 → 人工 review → 落地。Negatives 也按同样方式 review。
- **D2 覆盖率扩展 = 沿用 Phase A**：扩 relevant 列表，不动 matcher；增加 negatives 列表覆盖（确保 negatives 是真负例不是漏标的正例）。
- **D3 阈值清理 = Phase A 已完成**，本任务不再处理。
- **D4 顺序 = 按 fail 严重度排（最痛先做）**：
  1. cross_kb_negatives.jsonl (5 query) — 全套 fail，hit=-0.8 vs hashing
  2. fault_codes.jsonl (5 query) — hit=-0.6
  3. model_numbers.jsonl (5 query) — hit=-0.4
  4. tag_cooccurrence.jsonl (5 query) — hit=-0.2
  5. product_manuals.jsonl (14 query) — hit=-0.29 (最大但每条小)
  6. mixed_language.jsonl (5 query) — hit=-0.4
  7. tag_rerank_edge.jsonl (5 query) — hit=0 (最轻，做最后一遍 spot check)
- **D5 验收 = siliconflow CI 8/8 绿**：
  - `run_eval_ci.py --baseline siliconflow.json --embedder siliconflow` 全绿。
  - hashing CI 默认仍全绿。
  - pytest 全量不漂。
- **D6 hashing 重 capture + sanity = 沿用 Phase A** "hit/mrr/precision 不退化（recall 允许扩展性下降）"。

## Requirements

### Workflow（每套 suite 独立循环）

For each of the 7 suites in D4 order:
1. 跑 `scripts/relabel_eval_fixture.py --suite tests/fixtures/eval/<NAME> --output research/<NAME>-proposals.jsonl`
2. Claude 起草 `research/<NAME>-review.md`：每 query 候选清单 + 建议（覆盖 relevant + negatives 两个维度）
3. 用户 review（按 autonomous-iteration-mode：默认全部接受 AI 建议，仅在异常时叫停）
4. 落地 fixture 修改（扩 relevant / 调 negatives）

Phase B 完成时跑一次：
- 双 baseline 重 capture（hashing.json / siliconflow.json）
- 三项验收命令（pytest / hashing CI / siliconflow CI）

### Negatives 处理（Phase A 没显式处理，本任务专门加入）

- 现有 `negatives` 列表：每条 query review 时确认这些反例是否真的应当不在 top-K
- 如果 siliconflow 实际召回了某个标记为 negative 的 chunk，且语义上其实是合理答案 → 把它从 negatives 移到 relevant
- 如果 fixture 写"negatives 应当不在 top-K 1-2 名"但实际就是召不出来 → 该 negative 标注本身没用，可以放宽到"不在 top-K"或删除该 negative 字段

### 不动的部分

- scripts/relabel_eval_fixture.py 工具本身（Phase A 已就绪）
- run_eval_ci.py 默认行为（Phase A 已设 `--no-default-thresholds` 默认）
- src/tagmemorag/eval/matching.py 判定逻辑

## Acceptance Criteria

- [ ] 7 套 suite 全部完成 D4 顺序的 relabel 流程，决策记入各自 `research/<suite>-review.md`。
- [ ] 双 baseline 重 capture；hashing 在 hit/mrr/precision 不退化（recall 允许结构性下降）。
- [ ] `pytest tests/`：457+ passed。
- [ ] `scripts/run_eval_ci.py`（默认 hashing）8/8 绿。
- [ ] `scripts/run_eval_ci.py --baseline siliconflow.json --embedder siliconflow` 8/8 绿（**Phase B 的核心 AC**）。
- [ ] commit message 含 hashing-pre vs hashing-post + siliconflow-pre vs siliconflow-post 双 delta 表（pre 用 Phase A 后的 baseline 快照作为对照）。
- [ ] 文档：在 docs/wave-phase1-architecture.md baseline 段把"Phase B 接力中"改为"已完成"。

## Out of Scope

- 算法逻辑改动（src/tagmemorag/ 完全不动）。
- 新增 suite 或 manual fixtures。
- wave-readiness-flags 任务（Phase B 完成后下一个）。
- run_eval_ci.py 默认行为再次调整（保持 Phase A 末态 `--no-default-thresholds`）。

## Definition of Done

- 7 套 suite 全部 review + 落地 + 验收。
- siliconflow CI 8/8 绿（Phase A 没做到的核心标准）。
- Phase B research 目录归档每套 suite 的 proposals.jsonl + review.md。
- 文档同步（README + docs）。

## Research References

- `.trellis/tasks/archive/2026-05/05-17-eval-fixture-rewrite/` — Phase A 完整决策 + workflow 模板。
- `.trellis/tasks/archive/2026-05/05-17-eval-fixture-rewrite/research/coffee-review.md` — review.md 模板。
- `scripts/relabel_eval_fixture.py` — 重用工具。
