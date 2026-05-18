# T2 — QueryPlan + Budget contract + SQLite plan log

## Goal

Introduce a serializable, replayable, persistable `QueryPlan` object as the cross-cutting contract between API entry and the retrieval pipeline (Architecture v2 § A2). Add per-request `Budget` for early-exit control. Persist plans to per-KB SQLite (Architecture v2 § D6) so future eval-as-driver work (T5) and shadow-vs-active comparison (T1) have a real, queryable substrate.

This task does NOT add LLM-based query rewrites or HyDE; the first planner is a thin, rule-based wrapper that captures what already exists in the request body. The point of the slice is to **introduce the contract and persistence**, not to make the planner smart.

## Background / Known Context

Repo state inspected on 2026-05-18:

- `SearchRequest` (`src/tagmemorag/api.py:192`) already carries many plan-shaped fields: `question`, `top_k`, `source_k`, `steps`, `decay`, `amplitude_cutoff`, `aggregate`, `kb_name`, `filters`, `debug`, `core_tags`, `ghost_tags`.
- `RetrieveRequest` extends it with `token_budget`.
- `_search_impl` / `_retrieve_impl` consume those fields directly. There is no intermediate "plan" object today.
- Search feedback is persisted as JSONL at `feedback_log_path(kb, settings)` (`src/tagmemorag/retrieval_feedback.py`). The query is stored in plain text. Retention is unbounded.
- `pyproject.toml` has zero RDBMS dependency; SQLite is Python stdlib.
- `Settings.cache.enabled` exists; query caching is opt-in.

Architecture references:

- A2 § "QueryPlan and Request Budget" — schema, early-exit protocol, planner backends, persistence rules.
- D6 (PRD `architecture-v2`) — persist QueryPlan to per-KB SQLite; query raw text NOT stored, rewrites PII-masked, other fields stored as-is, retention configurable per KB.
- Memory: [[architecture-v2-followup-roadmap]] T2 row, [[eval-as-driver-mechanism]] (T2 unblocks the persisted plan set), [[t1-implementation-lessons]] for path/abstraction patterns to anticipate.

## Scope

### Code changes

1. **`QueryPlan` dataclass** (`src/tagmemorag/queryplan/plan.py`): schema_version, plan_id, kb_name, query_hash, query_rewrites (initially `[question]`), intent (initial: rule-based classifier returning a small enum), filters, strategy (which indexes participate), rerank (None for now; T3 fills it), budget, served_by_generation, created_at.
2. **`Budget` dataclass**: latency_ms, rerank_tier (`off|tier1|tier2`, default `off` until T3), max_evidence, allow_external_reranker.
3. **Rule-based planner** (`src/tagmemorag/queryplan/planner.py:build_plan`): takes (request, kb_name, settings) → QueryPlan. Initial intent classifier is keyword/regex driven; rewrites passthrough; filters extracted from `SearchFilters`.
4. **Early-exit protocol**: each long step in `_search_impl` / `_retrieve_impl` checks remaining budget; on exhaustion returns partial result with `warnings: ["<component>_skipped_due_to_budget"]`. NEVER raise on budget exhaustion.
5. **Plan log SQLite store** (`src/tagmemorag/queryplan/plan_log.py`): per-KB `{kb_root}/query_plans.db`, stdlib `sqlite3`, `PRAGMA user_version` migration, schema includes (plan_id, kb_name, query_hash, intent, filters JSON, strategy JSON, budget JSON, rerank JSON, served_by_generation, created_at, rewrites_masked JSON). Insert path is non-blocking on `/retrieve`: if the insert exceeds 2ms it's dropped + metrics counter incremented.
6. **PII mask hook** (`src/tagmemorag/queryplan/privacy.py`): pluggable mask function applied to rewrites before persistence. Initial implementation = passthrough with TODO; the hook exists so T4/operator can plug in real masking without changing the planner contract.
7. **`SearchRequest`/`RetrieveRequest` accept optional `budget` field**: `Budget | None`, default None means "use settings defaults".
8. **API responses gain `plan_id` field**: lets clients reference the persisted plan for feedback / replay.
9. **Settings additions**: `Settings.queryplan.persist_enabled` (default True), `Settings.queryplan.retention_days` (default 30), `Settings.queryplan.private_kbs` (list of KB names that opt out of persistence per A2 rule 4).

### Non-code

10. **Memory**: 1 reference memory pointing at the new module + admin contract. 1 feedback memory if T2 surfaces design lessons (similar to `t1-implementation-lessons`).
11. **architecture.md update**: A2 status badge moves from 🚧 to ✅.

## Decisions (ADR-lite)

### D1 持久化时机：同步基础字段 + 异步结果字段

**Context**：plan_id 必须在响应里立即可用（产品承诺：客户端拿 plan_id 立即可查/可反馈）；同时不希望主路径被 SQLite 故障拖累。
**Decision**：分两阶段写入。
- **同步阶段（在响应返回前）**：INSERT 基础字段（`plan_id`, `kb_name`, `query_hash`, `intent`, `filters_json`, `strategy_json`, `budget_json`, `created_at`）。这一段必须成功；失败时记 metric + 仍然返回响应，但 `plan_id` 用 in-memory 占位，response 里照常返回（消费者重试 SQLite 查询时仍可能 404，由文档说明边界）。
- **异步阶段（后台线程）**：UPDATE 补 `served_by_generation`, `evidence_ids_json`, `rerank_json`（T3 后填充）, `latency_ms_observed`, `warnings_json`。
- 实现：用一个进程内 `BackgroundWriter` queue，背后单 worker thread 顺序 flush；主线程不阻塞。
- 失败处理：基础字段 INSERT 失败 → metric `plan_log_insert_failed`；后台 UPDATE 失败 → metric `plan_log_update_failed` + 写一行结构化 log；都不影响主路径返回。
**Consequences**：
- SQLite schema 必须支持 partial row（结果字段都是 nullable），不能用 NOT NULL。
- 客户端如果在 plan_id 返回后立即查 SQLite，能拿到基础字段；结果字段可能要等 ~毫秒级延迟才出现。
- PRD 中"insert 超过 2ms 即丢弃"这条**作废**——B 方案下基础字段必须 INSERT 成功，不丢。

### D2 意图分类器范围：极简 2 类（A 方案）

**Context**：意图字段的实际效用取决于下游路由消费者；T2 阶段没有，T3 reranker 也用不上，T6 `/answer` 才会真用。提前做细分类是过度工程。
**Decision**：
- Schema 层保留完整 6 个 enum 值（与 architecture.md A2 一致）：`text_answer | table_lookup | troubleshooting | model_specific | visual_reference | out_of_scope`。
- 实现层第一版只产出 2 类：`text_answer`（默认）+ `out_of_scope`（黑名单关键词触发，例如纯 LLM 问题、与本 KB 完全无关问题）。
- `out_of_scope` 命中走"短路"路径：跳过检索、返回空 evidence + warning，仍然写 plan log。
- 实现位置：`src/tagmemorag/queryplan/intent.py`，单一函数 `classify(question: str, kb_name: str, settings) -> Intent`。
**Consequences**：
- 4 个保留 enum 在 T2 内永远不会被触发——这是有意的"接口稳定，实现先简后繁"。
- 黑名单触发关键词需要 admin 可调（可后续 T6 阶段加进 Settings）；T2 默认硬编码极小一组（"今天"、"翻译"、"股票"、"天气"等通用噪声）。
- `out_of_scope` 短路必须保留 plan log 行，否则未来反向研究"哪些问题被错判 out_of_scope"会无据可查。

### D3 Budget 默认值：从 `Settings.queryplan` 读（B 方案）

**Context**：客户端不传 budget 时需要兜底；硬编码模块常量调整成本太高，三层 SLA 没业务驱动。
**Decision**：
- 新增配置块 `Settings.queryplan` 含字段：`persist_enabled` / `retention_days` / `private_kbs` / `default_latency_ms` / `default_max_evidence` / `default_rerank_tier` / `default_allow_external_reranker`。
- 缺省值：`latency_ms=5000`（5 秒，宽松到当前 retrieve 不会触发 early-exit；T3 上线后可收紧到 3000）；`max_evidence=8`；`rerank_tier="off"`；`allow_external_reranker=True`。
- 客户端可在请求 body 里传 `budget` 字段覆写；未传则用 Settings 默认。
- 私有 KB 短路：当 `kb_name in Settings.queryplan.private_kbs` 时，强制 `allow_external_reranker=False` 且 `persist_enabled=False`（A2 § persistence rule 4）。
**Consequences**：
- 未来 API-key-级 SLA 分级需求出现时，升级路径 = 在 `build_plan` 多加一层 lookup（key → kb → global），契约不改。
- 5000ms 是保守起手值，不会改变现有任何请求的行为；T3 + T6 上线后会重新调。
- 隐私 KB 的双重短路（不进 reranker + 不写 plan log）写在 build_plan 顶部一次性处理，避免下游每个组件各自判断。

### D4 Early-exit 模型：共享 deadline（A 方案）

**Context**：组件间预算分配方式有"共享 deadline"、"预切份额"、"混合"三种。当前没有"组件 hang 住"的真实风险（同步函数；reranker 自带 vendor timeout），也没有"每阶段成本占比"的实测数据来支撑预切。
**Decision**：
- `Budget.deadline_at` 字段（float，由 `build_plan` 从 `time.monotonic() + latency_ms/1000` 设置）。
- 每个组件入口检查 `_BudgetGuard.exhausted()`，超时返回 partial result + warning，**永不抛异常**。
- partial result 形态：retrieval → 已检索到的 chunks 子集；evidence → 已构建的 evidence；context pack → 已塞入预算的部分；context_pack 空时 `/retrieve` 返回 `{evidence: [], context_pack: {items: []}, warnings: [...]}`。
- 组件不预先分配份额——谁先跑、跑得快谁多用。
- 实现位置：`src/tagmemorag/queryplan/budget.py:_BudgetGuard`，跨组件共用。
**Consequences**：
- T2 上线后用 plan log 跑几天，能反向算出真实"每阶段成本占比"，再决定是否升级到 C（共享 deadline + 每阶段最大份额）。
- 升级路径：给 Budget dataclass 加 `per_stage_max_share: dict | None = None`，契约不破。
- 当前 retrieve 路径会改：所有"长操作"前需要插入 guard 检查；这是 T2 实施时的主要扫描面。

### D5 SQLite schema：plan log 同时存 `served_by_generation` + `build_id`（B 方案）

**Context**：retire generation 后 `served_by_generation=N` 会成为孤儿引用；`build_id` 提供独立的"那次具体构建"溯源标记，且对 eval replay 很有用。
**Decision**：plans 表同时存两个字段。
- `served_by_generation INTEGER` — 用于 generation 维度索引、按代查询。retire 后历史 plan 这一字段仍存（不清空）。
- `served_by_build_id TEXT` — 不可变快照标记；写入时从 `GraphState.build_id` 读。
- 两个字段都是 nullable，由异步 worker 在主路径完成后 UPDATE。
**Schema**:
```sql
CREATE TABLE plans (
    plan_id TEXT PRIMARY KEY,
    kb_name TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    intent TEXT NOT NULL,
    filters_json TEXT,
    strategy_json TEXT,
    budget_json TEXT,
    rewrites_masked_json TEXT,
    served_by_generation INTEGER,    -- nullable; async update
    served_by_build_id TEXT,         -- nullable; async update
    rerank_json TEXT,                -- nullable; T3 fills
    evidence_ids_json TEXT,          -- nullable; async update
    latency_ms_observed INTEGER,     -- nullable; async update
    warnings_json TEXT,              -- nullable; async update
    created_at TEXT NOT NULL
);
CREATE INDEX idx_plans_kb_created ON plans(kb_name, created_at);
CREATE INDEX idx_plans_kb_generation ON plans(kb_name, served_by_generation);
CREATE INDEX idx_plans_kb_intent ON plans(kb_name, intent);
PRAGMA user_version = 1;
```
**Consequences**：
- ~30 bytes/row 额外开销，30 天滚动 KB 体量可忽略（~900KB / 1000 plan/day）。
- T5 replay tool 既能"按 generation 反查"也能"按 build_id 验证当时事实"，无需依赖 index.json 反查。
- 未来 schema bump 走 `PRAGMA user_version` 迁移。

### D6 现有 feedback.jsonl 与新 plan log 并行（A 方案 + 顺手加 plan_id）

**Context**：用户反馈日志（feedback.jsonl）和系统请求日志（query_plans.db）概念上重叠但语义不同；不该在 T2 里改既有 feedback 模块，否则任务范围会爆炸。
**Decision**：
- 旧 `feedback.jsonl` 维持不变，所有现有 `/search/feedback` `/retrieve/feedback` 路径不动。
- 新 SQLite plan log 独立存放在 `{kb_root}/query_plans.db`。
- **顺手加**：`SearchFeedback` dataclass 增加可选字段 `plan_id: str = ""`；`/search/feedback` 和 `/retrieve/feedback` 请求 schema 接受可选 `plan_id`；feedback.jsonl row 里相应字段。
- 客户端使用方式：`/search` 响应里拿 `plan_id` → 后续提交 feedback 时一并传回 → 历史 join 可用。
- 不实现 join 工具——T5 replay tool 阶段再做。
**Consequences**：
- T2 改动 `retrieval_feedback.py` SearchFeedback 字段（添加 + 序列化），现有 jsonl 解析仍兼容（缺字段当作空字符串）。
- 现有 admin feedback 页面行为不变。
- 未来 join feedback ↔ plan 是 SQL `WHERE plan_id IN (...)`，无需重构。

### D7 Cache hit 也写 plan log（A 方案）

**Context**：plan log 的核心价值是"真实流量画像"和 T5 eval 重放；cache hit 是真实流量的一部分，跳过会让 log 不完整。
**Decision**：
- `/search` 和 `/retrieve` 每次请求都新生成 `plan_id` 并写 plan log，无论 cache hit 还是 miss。
- plans 表新增列 `cache_status TEXT` (`"hit" | "miss" | "disabled"`)，由异步 update 阶段写入。
- cache hit 路径：仍构造新 QueryPlan、写基础字段；cache lookup 后异步 UPDATE `cache_status="hit"`、`served_by_build_id` 记录 cache 来源 build_id（可选 follow-up）。
- 响应 `plan_id` 始终是新生成的，**不复用 cached plan_id**——保证 plan log 的"每次请求一行"语义干净。
**Consequences**：
- cache hit 主路径多一次 SQLite INSERT（基础字段，~几毫秒）；当前流量级别可接受。
- plans 表 schema 加 `cache_status` 列；migration 走 user_version。
- T5 重放时可以选"全部 plan"或"仅 cache miss"，由 filter 决定。
- admin status / metric 端点未来可加"cache hit rate per intent"维度（不在 T2 范围）。

### D8 私有 KB 标记：yaml `private_kbs` 列表（A 方案）

**Context**：隐私属性是 ops 决策；不该混进 IndexGeneration schema（碰已稳定的 T1）；不该用文件名 hack。低频变更，重启生效可接受。
**Decision**：
- `Settings.queryplan.private_kbs: list[str]` — 列表形式，yaml 维护。
- 命中 `kb_name in private_kbs` 时 `build_plan` 走短路：
  - `Budget.allow_external_reranker` 强制 `False`
  - `plan._persist = False`（in-memory flag）→ plan_log 不入库
  - `plan_id` 仍生成并返回响应（客户端拿这个 ID 查 SQLite 会 404，**这是隐私承诺**：私有 KB 不留痕）。
- 不实现 in-memory 索引"列出私有 KB 的 plan"——这违反隐私意图。
- 文档明确写：私有 KB 失去 eval 重放能力，T5 不会处理它们。
**Consequences**：
- 实现简单，一处分支 + 一个 dataclass 字段（`_persist`，private=False 含义）。
- ops 调整私有列表 = 改 yaml + restart。
- 测试需覆盖：私有 KB 不写 plan，响应仍带 plan_id，外部 reranker 强制关闭。

## Open Questions

All 8 brainstorm questions resolved (D1–D8). Detail-level decisions deferred to `design.md`:

- exact JSON serialization order in plans table (canonical or sorted-key?)
- background writer queue capacity / overflow strategy
- exact "out_of_scope" keyword list for the rule-based intent classifier
- retention pruning trigger (cron-style task vs lazy on-write)

## Open Questions (originals, all resolved)

- ~~Q1 Plan persistence visibility~~ → resolved by D1 (sync basic + async result)
- ~~Q2 Rule-based intent classifier scope~~ → resolved by D2 (2 classes only)
- ~~Q3 Budget defaults~~ → resolved by D3 (Settings.queryplan, latency_ms=5000)
- ~~Q4 Early-exit shape~~ → resolved by D4 (shared deadline)
- ~~Q5 SQLite schema build_id~~ → resolved by D5 (both fields)
- ~~Q6 feedback.jsonl migration~~ → resolved by D6 (parallel + add plan_id)
- ~~Q7 Cache interaction~~ → resolved by D7 (write all, cache_status field)
- ~~Q8 Private KB marker~~ → resolved by D8 (yaml list)

## Requirements

- `QueryPlan` and `Budget` are first-class dataclasses with stable JSON serialization.
- Every `/retrieve` and `/search` call constructs a QueryPlan; the plan_id is returned in the response.
- Budget early-exit protocol observable: when budget is exhausted, response is structurally valid + carries warnings; no HTTP error.
- Plans persist to per-KB SQLite by default; private KBs opt out per Q8 decision.
- Privacy: raw query is NEVER inserted into SQLite — only `query_hash` and PII-masked rewrites.
- Schema migration via `PRAGMA user_version`; migration path documented for future schema bumps.
- Backward compatibility: existing API consumers (no budget field, no plan_id consumption) continue to work unchanged.
- Eval slice (per [[eval-as-driver-mechanism]]): existing fixtures + a synthetic plan-log fixture to verify replay semantics.

## Acceptance Criteria

- [ ] **Eval slice named** before `task.py start`.
- [ ] `QueryPlan` / `Budget` dataclasses defined with schema_version + JSON round-trip + immutable hashable identity.
- [ ] `build_plan(request, kb_name, settings)` produces a QueryPlan; rule-based intent classifier covers at least `text_answer` + `out_of_scope`; richer enum from Q2 decision.
- [ ] `/search` and `/retrieve` responses include `plan_id` field.
- [ ] Persisted plan rows match QueryPlan fields with raw query hashed; rewrites pass through PII mask hook before insert.
- [ ] Budget early-exit demonstrated by a unit test: forcing latency_ms=1 returns partial result + warning, never raises.
- [ ] Per-KB SQLite at `{kb_root}/query_plans.db`; plan_id is unique; `PRAGMA user_version` set.
- [ ] Existing tests pass; new unit tests cover plan construction, persistence, mask hook, early-exit, retention pruning, private-KB opt-out.
- [ ] architecture.md A2 status flips ✅; A2 storage layout note links to `query_plans.db`.
- [ ] No regression in `/search` response shape: `plan_id` is additive.

## Out of Scope

- LLM-based query rewriting (HyDE, multi-query, etc.) — pluggable backend slot exists but no LLM planner ships in T2.
- Reranker integration — `rerank: None` placeholder only; T3 fills it.
- T5 replay tool — T2 only ships the persistence; T5 builds the CLI on top.
- Real PII masking implementation — hook is a passthrough with TODO; ops/T4 can plug in real masking later.
- Postgres backend — T2 stays SQLite per [[architecture-living-doc-location]] D6.
- Settings yaml writeback — same discipline as T1 D12: process-internal mutation only.

## Research References

- `.trellis/spec/backend/architecture.md` § A2, § C9
- archived: `.trellis/tasks/archive/2026-05/05-17-architecture-v2/prd.md` D6 (SQLite per-KB)
- code: `src/tagmemorag/api.py` (SearchRequest, RetrieveRequest, _search_impl, _retrieve_impl), `src/tagmemorag/retrieval_feedback.py` (feedback_log_path), `src/tagmemorag/storage/atomic.py` (atomic write primitive — but SQLite uses its own WAL).
- memory: [[architecture-v2-followup-roadmap]], [[eval-as-driver-mechanism]], [[t1-implementation-lessons]], [[indexgen-mechanism-key-points]]
