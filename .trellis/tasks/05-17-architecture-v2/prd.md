# Architecture v2 — full redesign covering Phase 0-5 revisions and Phase 6-8 blueprint updates

## Goal

Produce a living architecture document at `.trellis/spec/backend/architecture.md` that:

1. Revises the design of the parts already implemented (Phase 0–5) to close production-blocking gaps identified during the Codex review and SF reranker research.
2. Updates the blueprint for the parts not yet implemented (Phase 6–8) so future execution tasks inherit a corrected, more honest baseline.
3. Replaces the archived `production-rag-architecture/design.md` as the single source of truth for system architecture going forward; the archive remains as a historical reference.

This task does not modify production code. Its only outputs are documentation and a roadmap for follow-up execution tasks.

## Background / Known Context

- Phase 0–5 已实施完毕（archive 任务：production-rag-architecture, chunk-lineage-ir, production-chunker, indexing-strategy-schema, retrieve-text-evidence-api, retrieve-inspect-feedback, visual-evidence-asset-pipeline, visual-evidence-retrieve-api）。
- Phase 6–8 仅有蓝图，尚未启动。
- 现存 design 文档藏在 archive 里，没有 living architecture doc。`.trellis/spec/backend/index.md` 当前指向 archive 任务文件作为合同源。
- WAVE 三个 readiness flag 实证后默认全关（[[wave-readiness-flags-empirical-keep-off]]），但 archive design 仍把 WAVE 列在 "Strengths Worth Preserving"。
- SF 实测事实（已坐实，写入 design）：
  - `POST https://api.siliconflow.cn/v1/rerank`
  - `Qwen/Qwen3-Reranker-0.6B`：32K context，¥0.07/M token，L0 RPM 2000 / TPM 1M
  - `instruction` 字段为 Qwen3 系列独有
  - `max_chunks_per_doc` / `overlap_tokens` 仅 BGE/BCE 支持，Qwen3 不支持，超长文档需我方截断
  - 顺手发现：`Qwen/Qwen3-VL-Reranker-8B` 提供多模态 rerank，可用于 Phase 7B
- Codex 评审已确认下列原则：QueryPlanner 先做契约后做实现、Tier-2 LLM-judge reranker 默认关、流式延后到 Phase 6 前后、WAVE 改标 experimental。

## Scope

### A. Phase 0–5 现网修订（contract-level depth）

A1. ID 系统分裂：`chunk_id`（不含 embedding）/ `vector_point_id`（含 embedding model id+version）
A2. QueryPlan + Request Budget（横切层）
A3. Reranker 一等组件（含 SF Qwen3-Reranker 集成规范、tier 分级、fallback、校准）
A4. Index Generation（双库并行 / shadow / split / swap / retire）
A5. WAVE 重标 + production-grade 自评收紧

### B. Phase 6–8 蓝图修订（direction-level depth）

B6. Phase 6 `/answer`：多轮 session、tool-calling 边界、refusal 契约、faithfulness eval 方法论、generation cache、流式
B7. Phase 7 拆轨：7A OCR（layout-aware vs char-only 路线对比）+ 7B 视觉检索（encoder vs reranker 分离 + SF VL-Reranker-8B 选项）
B8. Phase 8 连接器：DocumentElement 输出契约、软删除、ACL 适配、schema drift、webhook vs polling

### C. 横切原则

C9. eval-as-driver 机制化：每次 `/retrieve` 的 QueryPlan 自动构成滚动 eval 集
C10. 文档诚实性：WAVE 重标 + production-grade 自评收紧

## Decisions (ADR-lite)

### D1 文档写作风格：重写整本（rewrite）

**Context**：v2 架构修订涉及 10 条改动横跨 5 个已实施 phase 与 3 个未实施 phase，团队规模 = 1 人 + AI agent。
**Decision**：写一份完整自洽的新 architecture.md，archive 里旧 design 保持不动作为历史档案。
**Consequences**：
- 文档必须用清晰状态标记区分 "✅ 已实施" / "🚧 v2 修订中" / "📋 蓝图"。
- 修订内容用"目标态描述"风格写，旧版差异通过末尾的 changelog 段落体现，不在正文逐处对比。
- 后续 v3 沿用同样纪律：当前 living doc 进 archive，新版上线。

### D2 Phase 6–8 蓝图修订深度：方向卡片 + 关键开放问题清单（折中 C）

**Context**：Phase 6–8 启动时间不定，越深的预设越容易过期。当前任务范围又必须给后续任务一个起点。
**Decision**：Phase 6–8 每节包含三段：方向描述、必须在任务启动时回答的开放问题清单、明确的"现在不做什么"。不锁定具体方案、模型、库选型。
**Consequences**：
- Phase 6–8 启动时仍需独立 brainstorm，但起点不再为零。
- 选型决策（视觉 encoder、faithfulness eval 方法、multi-turn state 存储）留到那时根据当时的 eval 数据和业界进展决定。
- 文档需明确区分 A 区（contract-level）与 B 区（direction + open questions）的深度差异。

### D3 后续执行任务路线图：在 PRD 末尾拟"派工单"，但不预建 task

**Context**：v2 修订条目互相依赖（QueryPlan 依赖 IndexGeneration 依赖 ID 分裂等），不在结尾固化执行顺序，下次重启时仍需重新梳理。
**Decision**：本任务交付物之一是后续执行任务路线图表（标题 + 依赖 + 优先级），写在 architecture.md 末尾或 PRD 末尾的"Follow-up Tasks"段落。**不**通过 `task.py create` 预建任何后续任务，只列骨架清单。
**Consequences**：
- 启动后续任务时直接照表 `task.py create`，避免重做依赖分析。
- task list 不会被长期 planning 状态的远期任务污染。
- 路线图表要包含至少：A 区每条改动如何拆分（合并 / 单独）、B 区每个 phase 的启动任务、C 区横切原则的落地任务。

### D4 选型信息分层：合约稳定 + 附录给参考实现

**Context**：SF Qwen3-Reranker / BGE / VL-Reranker 等具体型号信息已实测可用，但定价/限速/模型 id 是会随供应商改动的字段，写进合约层会让文档天天动。
**Decision**：架构文档采用两层结构。
- **正文**：写稳定的合约（接口、字段、cache key、tier 分级、calibration 要求、降级顺序的抽象形态）。
- **附录 "Reference Implementations"**：写截至本任务完成日的具体型号、定价、限速、API 实测细节，并在标题上明确"截至 YYYY-MM-DD"。
该纪律同时套用于 A3（Reranker）与 B7（Phase 7B 视觉）以及任何未来引入的供应商绑定决策。
**Consequences**：
- 实测的 SF 信息不浪费，写在附录里。
- 供应商改价/换模型 id 时改附录，正文不动。
- 解决 Q5 与 Q8 同一类问题：型号选择不写死，但实测参考保留。

### D5 IndexGeneration 模型：双库并存 + 一键切换（B）

**Context**：当前 rebuild 是一刀切（覆盖 Qdrant collection / GraphState 引用），换 embedder/chunker 期间 KB 短暂不可用且无回滚。已查清：Qdrant collection 名 = `{prefix}_{kb}`（无 generation），`AppState.swap_kb` 直接替换引用，原子写仅在文件级。
**Decision**：架构合约采用双库并存 + 一键切换形态。
- Qdrant collection 名增加 generation 后缀：`{prefix}_{kb}_g{N}`
- 文件存储增加 generation 子目录：`{kb}/g{N}/...`
- `AppState` 同时持有 active 与 shadow 两代 GraphState
- 通过 admin API 触发 swap（active ↔ shadow）与 retire（删除旧 generation）
- 触发 generation 升级的版本字段：`parser_version` / `chunker_version` / `embedding_model_id` / `embedding_model_version` / `index_schema_version` 任一变更
- **不**实现灰度切流；真实流量对比通过离线重跑持久化 QueryPlan 集达到（与 C9 eval-as-driver 联动）
**Consequences**：
- 本任务只写合约形态，不动代码；后续独立执行任务实施。
- 文档需要给出 generation 升级触发条件、命名规则、admin API 形态、retire 时机、回滚边界。
- 双倍存储成本仅在 rebuild 窗口期出现；retire 后回到单代。

### D6 QueryPlan 持久化：SQLite per-KB

**Context**：当前项目零 RDBMS 依赖，反馈日志走 jsonl（`search-feedback.jsonl`）。eval-as-driver 机制需要可被 SQL 查询/聚合的 plan 存储，jsonl 不胜任，PG 又过重。
**Decision**：QueryPlan 持久化采用 SQLite，每个 KB 一份独立文件（`{kb}/query_plans.db`）。
- 隐私：query 原文不入库（只存 hash）；rewrites 入库前做 PII mask 后再存原文（保留 eval 价值）；其它结构化字段（intent / filters / budget / reranker_id / calibrated scores / served_by_generation / citation_ids）入库
- 与现有 `search-feedback.jsonl` 关系：jsonl 继续作为 append-only 审计源；SQLite 作为可查询副本，定期/即时从 jsonl 落入（或同时双写）。具体方式留到执行任务定。
- 加入 storage 抽象层 `storage/sqlite_planlog.py`，与 `json_*` / `npz_*` / `qdrant_*` 平级。
- 不引入 ORM；用 stdlib `sqlite3` + 显式 SQL，schema 走 `PRAGMA user_version` 做迁移。
**Consequences**：
- pyproject.toml 不增加依赖（SQLite 是 Python 标准库）。
- v2 文档新增 "Storage Backends" 一节，把 SQLite 加入分层。
- 多机部署时 SQLite 不共享，但当前架构是单机单租户，迁 PG 留作未来 D-级决策。
- D5（IndexGeneration）的 active/shadow 对比落到这个 plan store 上：通过重放 plan 集对两代库分别打分。

## Open Questions

All blocking questions resolved during brainstorm (D1–D6). Remaining items are non-blocking and will be settled while writing `architecture.md`:

- Q2 living doc 与 archive 的交叉引用形态（顶部 metadata 块 vs 文末 changelog vs 两者都有） — non-blocking, decide while drafting.

## Requirements

- 输出 `.trellis/spec/backend/architecture.md` 第一版，覆盖 A/B/C 全部条目。
- A 区每条必须给出可被后续执行任务直接采用的合约（schema 字段、ID 派生公式、API 行为约定）。
- B 区每条给出方向 + 取舍 + 必须在执行任务 PRD 阶段坐实的开放问题列表。
- C 区给出机制化定义而非口号。
- archive 内 production-rag-architecture/design.md 保持不动；新文档头部引用历史。
- 任务末尾产出后续执行任务路线图（标题 + 依赖 + 优先级，不含实现细节）。

## Acceptance Criteria

- [ ] `.trellis/spec/backend/architecture.md` 已创建并覆盖 A1–A5、B6–B8、C9–C10 全部条目
- [ ] `.trellis/spec/backend/index.md` 更新为指向新 living doc，archive 文档降级为历史参考
- [ ] 每条 A 区改动有明确的 before/after 对比段，包含 schema 或合约级细节
- [ ] 每条 B 区蓝图给出"必须在执行任务前回答"的开放问题清单
- [ ] WAVE 在文档中标记为 experimental, default-off，与 [[wave-readiness-flags-empirical-keep-off]] memory 对齐
- [ ] 后续执行任务路线图列出至少：A1+A4 合并任务、A2+A3 合并任务、Phase 6 启动任务，含依赖与优先级
- [ ] 文档不引入未坐实的供应商/模型选型（视觉 encoder 路线写为待 eval 决定）
- [ ] 全文不出现 "production-grade" 单方面自评，改为目标状态描述

## Out of Scope

- 不修改现网代码
- 不创建后续执行任务（只列骨架清单）
- 不实施 SF Reranker 接入
- 不更改 archive 内 production-rag-architecture/design.md 内容
- 不做 Phase 6–8 的代码探索

## Research References

- archive: `.trellis/tasks/archive/2026-05/05-17-production-rag-architecture/design.md`
- SF rerank API（实测）: https://docs.siliconflow.cn/cn/api-reference/rerank/create-rerank
- SF Qwen3-Reranker-0.6B 模型详情（实测）: https://cloud.siliconflow.cn/me/models?types=rerank
- Memory: [[wave-readiness-flags-empirical-keep-off]], [[fixture-eval-ground-truth-fragility]], [[only-port-vcp-no-calibration]]
