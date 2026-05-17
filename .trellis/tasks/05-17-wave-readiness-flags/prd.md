# wave-readiness-flags — 决定 3 个 wave_phase1 默认 false flag 翻开

## Goal

让 wave-RAG 的 3 个算法 phase 真正"上线"：评估 `cross_domain_resonance_enabled` /
`intrinsic_residuals_enabled` / `geodesic_rerank_enabled` 各自翻开 vs 不翻开
对生产 embedder（Qwen3-VL-Embedding-8B）下的 4 个 strict eval suite
（coffee / mixed_language / product_manuals / tag_rerank_edge）影响，
然后基于实证决定**默认值**和**生产灰度**。

不再让 Phase 3 / 3.5 / 4 算法"接通了但默认 off 永远不跑"——这是用户 Goal
"算法真实可行"的最后一公里。

## Background

经过 Phase 1-4 + baseline + fixture rewrite (Phase A/B) 后的当前状态：

- `wave_phase1.spike_enabled = True`（已翻开，Phase 1 默认行为）
- `wave_phase1.cross_domain_resonance_enabled = False`（Phase 3 默认 off）
- `wave_phase1.intrinsic_residuals_enabled = False`（Phase 3.5 默认 off）
- `wave_phase1.geodesic_rerank_enabled = False`（Phase 4 默认 off）

eval CI 双轨：
- hashing.json：默认 CI 门禁，8/8 strict 全绿
- siliconflow.json：production embedder informational gate，4 strict + 4 stress-test (informational) = 8/8 整体绿

## 评估方法

对每个 flag，独立评估"flag-on vs flag-off"在 4 strict siliconflow suite 上的指标
变化（hit_at_k / mrr / precision_at_k / recall_at_k）。判断翻开是否：

- 显著改善（任意 metric +0.05 以上 在多套 suite）→ **翻开默认值**
- 持平或微小变化（|delta| < 0.02）→ **保持默认 off**，文档说明 ops 可灵活开
- 显著退化（任意 metric -0.05 以上 在多套 suite）→ **保持默认 off**，记录调参建议

测试组合（5 种）：

| 配置名 | resonance | residuals | geodesic | 用途 |
|---|---|---|---|---|
| baseline | off | off | off | Phase A/B 末态对照 |
| only-resonance | on | off | off | Phase 3 单独效果 |
| only-residuals | off | on | off | Phase 3.5 单独效果 |
| only-geodesic | off | off | on | Phase 4 单独效果 |
| all-on | on | on | on | 三 flag 叠加效果 |

## Decisions

- **D1 评估范围 = 4 strict siliconflow suite**（不含 4 informational stress-test）。
  理由：strict suites 是生产质量信号，stress-test 是 long-term 监测点不参与 readiness 决策。
- **D2 评估方式 = 实测 5 个配置 × 4 suite × 4 metric = 80 数据点表，diff vs baseline**。
  写一个 `scripts/diag_wave_readiness_flags.py` 跑全套并输出 diff 表。
- **D3 默认翻开判据**:
  - 翻开：≥2 个 metric 在 ≥2 个 strict suite 上改善 ≥ +0.03，无 metric 在任何 strict suite 退化 > 0.05
  - 保持 off：不满足"翻开"条件 OR 任意 strict suite 任意 metric 退化 > 0.05
- **D4 决策粒度 = 每个 flag 独立判定**（不强求 all-or-nothing）。
  即可能 resonance 翻 / residuals 不翻 / geodesic 翻，组合三个独立决议。
- **D5 翻开实施 = 改 src/tagmemorag/config.py 的 `Field(default=False)` → `True`**。
  改动后：
  - hashing CI 必须仍 8/8 绿（默认门禁不漂）
  - siliconflow CI 4 strict + 4 informational 仍整体绿
  - pytest 全量绿（455+ tests）
  - 重 capture 双 baseline 反映新默认行为
- **D6 灰度建议 = 生产可分阶段翻**：本任务只改 default 值，运维侧仍可通过 config / env 显式 override。

## Requirements

### 工具

- 新增 `scripts/diag_wave_readiness_flags.py`：
  - 跑 5 个配置（baseline + 3 only-* + all-on）× siliconflow embedder × 4 strict suite
  - 输出 diff 表（per-suite per-metric per-config delta vs baseline）
  - 复用 build_eval_baseline 的 `_with_retry` + smoke check
  - 输出归档到 `research/readiness-flags-diff.txt`

### 决策

- 基于 diff 表按 D3 判据 + D4 粒度，对每个 flag 独立给出 keep-off / flip-on 建议
- 决策记入 `research/readiness-decision.md`
- 用户 review 后落地

### 实施（如有 flag 翻开）

- 改 `src/tagmemorag/config.py` 的对应 `Field(default=False)` → `True`
- 更新现有"baseline invariance" e2e 测试或单测断言（如果"现状"现在变化了）
- 重 capture hashing.json + siliconflow.json
- 文档更新：README + docs/wave-phase1-architecture.md 标注新默认值

### 验收

- pytest 全量绿
- hashing CI 默认 8/8 strict 绿
- siliconflow CI 8/8 整体绿（4 strict + 4 informational）
- diff 表归档 + 决策文档归档

## Acceptance Criteria

- [ ] `scripts/diag_wave_readiness_flags.py` 跑通并输出完整 diff 表归档
- [ ] `research/readiness-decision.md` 含每个 flag 的 keep-off / flip-on 决策 + 理由
- [ ] 翻开的 flag 在 src/tagmemorag/config.py 改默认值；保持 off 的 flag 不动
- [ ] 双 baseline 重 capture（如有 flag 翻开）
- [ ] pytest / hashing CI / siliconflow CI 三项验收全绿
- [ ] 文档同步（README + docs/wave-phase1-architecture.md）

## Out of Scope

- 修改 wave_phase1 算法逻辑或常数参数（spike_firing_threshold 等）
- 增减 fixture suite
- 改 hashing.json 在 CI 默认门禁地位
- 自动 ops 翻 flag 工具（人工 config / env 即可）
- 多 model embedder 评估（只评 Qwen-VL）

## Definition of Done

- 3 个 flag 各自有清晰的"是否翻开"决议 + 实证依据
- 翻开的 flag 落到默认配置 + 不破坏 baseline
- 文档反映新现状

## Research References

- `.trellis/tasks/archive/2026-05/05-17-eval-fixture-rewrite/` — Phase A/B 结论
- `.trellis/tasks/archive/2026-05/05-16-wave-phase4-geodesic-rerank/` — Phase 4 默认 off 哲学
- `scripts/diag_geodesic_rerank.py` — diag 脚本模板
- `scripts/run_eval_ci.py` — 双轨 CI 工具
