# T3 — Reranker first-class component + SF Qwen3-Reranker-0.6B integration

## Goal

Introduce a vendor-neutral `Reranker` Protocol and ship one production-ready integration (SiliconFlow's `Qwen/Qwen3-Reranker-0.6B`) as the Tier-1 online reranker. Wire reranking into the `/retrieve` pipeline AFTER candidate retrieval and BEFORE evidence building, gated by `Budget.rerank_tier` and `Budget.allow_external_reranker`. Calibrate raw scores before any hybrid fusion. Make the rerank step a first-class participant in QueryPlan + plan log so eval and replay (T5) can analyze rerank impact.

This task is the third and final P1 task on the architecture-v2 follow-up roadmap. After T3, the platform is "ready for Phase 6 /answer" per architecture.md.

## Background / Known Context

Repo state (2026-05-18):

- `/retrieve` pipeline (`api.py:_retrieve_impl`): plan → embed → execute_search → build_retrieve_response. No rerank step today.
- `execute_search` (in `src/tagmemorag/search.py`) returns `SearchExecution.results: list[SearchResult]` with `score`, `chunk_id`, `text`, etc.
- `build_retrieve_response` consumes those results and produces evidence + context_pack.
- `QueryPlan.rerank: dict | None` is None placeholder (T2 Slice 1) — T3 fills it.
- `QueryPlan.budget.rerank_tier` is "off" by default (T2 D3) — T3 turns it into a real switch.
- `QueryPlan.budget.allow_external_reranker` (T2) is an ACL gate; private KBs force False.
- T2 plan_log has nullable `rerank_json` column ready to receive our payload.
- `pyproject.toml` has no HTTP client beyond `httpx>=0.27` (already used in tests + manual library bundle).
- SF environment variable: `SILICONFLOW_API_KEY` (already referenced in `Settings.model.api_key_env`).

SF rerank API facts (verified live 2026-05-17):

- `POST https://api.siliconflow.cn/v1/rerank`
- Auth: `Authorization: Bearer $SILICONFLOW_API_KEY`
- Body: `{model, query, documents, top_n?, return_documents?, instruction?, max_chunks_per_doc?, overlap_tokens?}`
- `instruction` field: ONLY supported by Qwen3-Reranker family (0.6B / 4B / 8B). BGE/BCE ignore it.
- `max_chunks_per_doc` / `overlap_tokens`: ONLY supported by BGE/BCE. Qwen3 needs caller to pre-truncate.
- Response: `{id, results: [{index, document?, relevance_score}], meta: {tokens, billed_units}}`
- `relevance_score`: NOT guaranteed normalized; must calibrate before fusion (architecture A3).
- Qwen3-Reranker-0.6B: 32K context, ¥0.07/M token (input only), L0 RPM 2000 / TPM 1M.

Architecture references:
- `.trellis/spec/backend/architecture.md` § A3 — full Reranker contract.
- Memory: [[arch-vendor-specifics-discipline]] — vendor specifics confined to Appendix A.
- Memory: [[t2-queryplan-mechanism-key-points]] — `QueryPlan.rerank` shape; `Budget.rerank_tier`.

## Scope

### Code changes

1. **`Reranker` Protocol** (`src/tagmemorag/reranker/base.py`): vendor-neutral interface.
2. **`RerankDoc` / `RerankResult`** dataclasses.
3. **SF Qwen3 adapter** (`src/tagmemorag/reranker/siliconflow.py`): httpx client, retry, circuit breaker, per-doc pre-truncation.
4. **NoopReranker** (`src/tagmemorag/reranker/local_fallback.py`): passthrough fallback chain element.
5. **Dispatcher** (`src/tagmemorag/reranker/dispatcher.py`): tier routing, ACL gate, fallback chain.
6. **Score calibration** (`src/tagmemorag/reranker/calibration.py`): z-score baseline; pluggable.
7. **Hybrid fusion adapter**: insert rerank stage between execute_search and build_retrieve_response in `/retrieve`.
8. **Cache** (in-memory LRU): key = `(reranker_id, reranker_version, instruction_hash, normalized_query, chunk_id_set_hash)`.
9. **QueryPlan.rerank fill**: build_plan attaches `RerankSpec`; dispatcher reads from plan.
10. **Plan log rerank_json**: dispatcher writes vendor_used / calibrated / latency_ms / fallback_used / warnings.
11. **Settings.reranker** block: enabled, provider, model_id, model_version, instruction, top_n, query_token_budget, instruction_token_budget, circuit_breaker_threshold, retry_max, cache_max_entries.
12. **Fail-safe wiring**: errors NEVER raise to API; fallback chain → noop; metric emitted.

### Non-code

13. **architecture.md A3**: status 🚧 → ✅; T3 shipped paragraph.
14. **architecture.md Appendix A**: SF Qwen3-Reranker-0.6B reference confirmed/dated.
15. **Memory**: 1 reference memory (T3 mechanism key points) + optional implementation lessons.

## Decisions (ADR-lite)

### D1 Rerank 位置 + 候选窗（B 方案）

**Context**：execute_search 当前默认 top_k=5，reranker 没空间发挥；rerank 真正的价值在"召回更多候选 + 精排"。
**Decision**：在 execute_search 之后插 rerank 阶段。`/retrieve` 时把 execute_search 的 top_k **扩大到 `Budget.rerank_candidates_n`**（默认 100），reranker 输出 `RerankSpec.top_n`（默认 20），下游 evidence/context_pack 再截到用户原本的 top_k。
- `Budget.rerank_candidates_n: int = 100` — 粗筛候选窗
- `RerankSpec.top_n: int = 20` — 精排后保留数
- 用户的 `request.top_k` 仍控制最终 evidence 上限（不变）。
- `/search`（legacy 兼容端点）**不改**，仍按 `request.top_k` 走 execute_search，无 rerank 阶段。
- rerank 关闭时（`Budget.rerank_tier="off"` 或 ACL 短路）`/retrieve` 退化到当前行为：execute_search 仍用 `request.top_k`，无候选窗扩张。
**Consequences**：
- `/retrieve` 在 rerank 开启时 execute_search 的工作量从"返回 5"涨到"返回 100"——主要影响 vector ANN 阶段的 top-K，但 Qdrant/NPZ 都已支持参数化，没结构性问题。
- 用户感知零变化（最终 top_k 不变）。
- 当 `top_n < rerank_candidates_n` 时 reranker 完成精排；当 `top_n >= rerank_candidates_n` 时退化为"只重排不裁剪"。
- D 字段命名："候选窗"在 Budget 里（运行时预算），"精排数"在 RerankSpec 里（rerank 配置）——分开避免概念混淆。

### D2 Score 校准 day-1：min-max 归一化（B 方案）

**Context**：reranker `relevance_score` 不保证分布形态；T3 暂不做 hybrid fusion，但合约不该锁死"无校准"。
**Decision**：默认 `MinMaxCalibrator` → batch 内 min-max 到 [0, 1]。
- 抽象接口 `Calibrator` Protocol：`name` + `calibrate(raw_scores) -> list[float]`。
- 内置 4 种：`MinMaxCalibrator`（默认）、`ZScoreCalibrator`、`SigmoidCalibrator`、`IdentityCalibrator`。
- `Settings.reranker.calibrator: Literal["minmax", "zscore", "sigmoid", "identity"] = "minmax"`。
- `RerankResult` 同时携带 `raw_score` 和 `calibrated_score`，plan log 都存。
- 单元素、所有元素相等等退化情况：返回全 0.5（标识"无信息"）；不抛异常。
**Consequences**：
- T3 阶段下游不做 fusion（reranker 输出顺序就是最终顺序）；calibrated_score 是 plan log 字段+未来 fusion 的预备。
- swap 校准方式不需要改业务代码——改 Settings 一行。
- raw 与 calibrated 双存，运营/eval 研究时能看分布。

### D3 Rerank cache：单进程 in-memory LRU（B 方案）

**Context**：reranker 调用花钱；相同 query 重复打 vendor 浪费；当前规模不需要持久化或共享 cache。
**Decision**：`src/tagmemorag/reranker/cache.py:RerankCache` — in-memory LRU。
- Cache key 5 元组：`(reranker_id, reranker_version, instruction_hash, query_hash, chunk_id_set_hash)`。
- Cache value：`list[(chunk_id, raw_score, calibrated_score)]`。
- **Invariant**：cache key **不含 generation**——同一 chunk_id 在 g1 和 g2 的 rerank 分数应该一致（reranker 不依赖向量特征）；T1 generation swap 不需清 cache。
- 设置：`Settings.reranker.cache_enabled: bool = True`，`Settings.reranker.cache_max_entries: int = 5000`。
- 进程重启 cache 清空，可接受（冷启动重新预热）。
- 未来升级路径：替换 LRU 为 SQLite-backed key-value store；cache key/value 形态不变。
**Consequences**：
- 多进程部署不共享 cache（首次预热每个进程独立）；当前单进程不影响。
- LRU 实现可用 stdlib `functools.lru_cache` 或 `collections.OrderedDict`，避免新依赖。
- cache miss 时仍走 vendor + 写入 cache；cache hit 时跳过 vendor，但 plan log 仍写一行（标 `cache_status="hit"` 在 rerank_json 内部，与 T2 顶层 cache 区分）。

### D4 Vendor 失败处理：retry 1 次 + 简化熔断 + Noop 降级

**Context**：reranker 走外部 HTTP，必然偶发失败；不能影响主路径。
**Decision**：
- **Retry**：HTTP 5xx / 超时 / 连接错误 → 等 200ms 退避 → 重试 1 次。HTTP 4xx（除 429）→ 不重试直接降级（客户端配置错误，重试无用）。429 同 5xx 处理。
- **简化熔断**：连续 N 次失败（默认 3）后熔断打开，**冷却 30 秒**期间所有请求走降级。冷却到期后下次请求重新尝试，成功清零，失败再 +1。无独立 half-open 状态。
- **降级行为**：vendor 失败 / 熔断打开 / ACL 禁用 → fallback chain → `NoopReranker`（保留 execute_search 原排序）。响应 `warnings: ["reranker_fallback:<reason>"]`；plan log `rerank_json` 写 `vendor_used="noop"` + 失败原因。
- **错误码永不抛**：dispatcher 捕获所有 reranker 异常；API handler 不感知。
- 配置字段：
  - `Settings.reranker.retry_max: int = 1`
  - `Settings.reranker.retry_backoff_ms: int = 200`
  - `Settings.reranker.circuit_breaker_threshold: int = 3`
  - `Settings.reranker.circuit_breaker_cooldown_seconds: int = 30`
- 熔断器实现：进程内 `CircuitBreaker(threshold, cooldown_s)` 持有 `failures: int` + `opened_at: float | None`。
**Consequences**：
- 失败路径最多多 ~200ms 延迟；与 Q9 BudgetGuard 决策联动。
- 多进程部署熔断器各自独立（短期不共享 vendor 状态视角），可接受。
- T5 的 plan log 重放可以反向研究 fallback rate；admin 端点暴露 circuit_breaker 状态留待 T5。

### D5 超长 chunk 处理：截断 + 上报（A 方案）

**Context**：Qwen3-Reranker-0.6B 32K context；当前 chunker max_chars=1200 远低于上限，正常路径不触发，但需要兜底。
**Decision**：
- 超过单 doc 上限的 chunk → 按 char 截断到 `max_doc_chars`（粗估，非 tokenizer），保留全部 doc 进入 rerank。
- `RerankResult` 包含 `truncated_chunk_ids: list[str]`；plan log `rerank_json` 包含 `truncated_count`。
- 配置（SF Qwen3 adapter）：
  - `Settings.reranker.max_seq_length: int = 32768`
  - `Settings.reranker.query_token_budget: int = 256`
  - `Settings.reranker.instruction_token_budget: int = 64`
  - `max_doc_chars` = `(max_seq_length - query_budget - instruction_budget) * 4 - 4096`（4 chars/token 粗估，留 4K buffer 安全空间）
- 中文友好：char-based 截断对中文偏保守（中文 1 char ≈ 1.5-2 tokens），不会真超 context。
**Consequences**：
- 不丢候选（不像 B 方案），rerank 看到的是 doc 头部，被截断的 doc 分数可能略低，但可控。
- 不模拟 max_chunks_per_doc / overlap_tokens（Qwen3 不支持这两个字段，不强行实现）。
- 截断比例如果在 plan log 里持续偏高，是 chunker 配置或对抗输入的信号 → admin 监控。

### D6 默认开关：feature flag `Settings.reranker.enabled` 默认 False（C 方案）

**Context**：reranker 是新外部依赖；按 [[wave-rag-flag-default-off-discipline]] 精神先装不开；ops 改 yaml 一刀启用。
**Decision**：
- `Settings.reranker.enabled: bool = False` — 全局开关。
- `Settings.reranker.default_tier: Literal["off", "tier1", "tier2"] = "tier1"` — enabled 时的默认 tier。
- 解读规则：
  - `enabled=False`：所有请求 `Budget.rerank_tier` 强制 `"off"`（无视客户端传值，避免误开启）。
  - `enabled=True` 且客户端未传 `rerank_tier` → 用 `default_tier`。
  - `enabled=True` 且客户端传 `rerank_tier` → 用客户端值。
- 这条解读在 `build_plan` 里实现（构造 Budget 时强制约束 rerank_tier）。
**Consequences**：
- T3 部署后行为零变化（与 T2 完全一致）；ops 验证 cost/latency/fallback 无问题后改 yaml 一刀开启。
- 升级路径：T3 ship → 第 1 周观察 → ops `enabled=True` → 个别 Tier-2 实验。
- 反向回滚：改 yaml 关 `enabled` = 即时回到 T2 行为，无需重新部署代码。
- 客户端零改动。

### D7 BudgetGuard 与 reranker：预算紧主动跳过 + httpx 超时按剩余预算（B 方案）

**Context**：reranker 调用 100-300ms 常态，可能抖动到秒级；与 T2 D4"共享 deadline"原则一致——不预切预算但给下游留最小工作量。
**Decision**：
- 进 reranker 阶段前 `guard.remaining_ms() < Settings.reranker.min_budget_ms`（默认 500ms）→ 直接走 noop 降级，记 `warnings: ["reranker_skipped_due_to_budget"]`。
- 否则调用 vendor，httpx timeout = `min(remaining_ms - 200ms, hard_timeout_ms)`（留 200ms 给 evidence/context_pack）。
- 配置：
  - `Settings.reranker.min_budget_ms: int = 500`
  - `Settings.reranker.hard_timeout_ms: int = 3000`
  - `Settings.reranker.downstream_reserve_ms: int = 200`
- 超时仍走 D4 失败路径（retry 1 次→熔断/降级）。
**Consequences**：
- 预算紧的请求 reranker 主动放弃，下游始终能跑出 evidence/context_pack。
- min_budget=500ms 是经验值；运行后 plan log 可统计"实际跳过率"，T5 阶段调优。
- vendor adapter 接收 budget_ms 参数（已写在 architecture A3 contract 里），dispatcher 据此设 httpx timeout。

## Open Questions

All 7 high-impact brainstorm questions resolved (D1–D7). Detail-level items deferred to `design.md`:

- exact `CircuitBreaker` thread-safety (lock granularity)
- LRU impl choice (`functools.lru_cache` vs `OrderedDict`)
- `reranker_id` formatting convention (`"qwen3-reranker-0.6b@siliconflow"` proposed)
- whether to expose admin endpoint for circuit breaker state (deferred to T5)

## Originals (all resolved)

- ~~Q1 Where in pipeline does rerank happen + Q2 top_n~~ → D1 (after execute_search; candidates=100, top_n=20)
- ~~Q3 Calibration day-1 default~~ → D2 (min-max)
- ~~Q4 Cache scope~~ → D3 (in-memory LRU, generation-independent)
- ~~Q5/Q6 Circuit breaker + retry~~ → D4 (retry 1 + simplified breaker N=3, cooldown=30s)
- ~~Q7 Truncation~~ → D5 (truncate by chars; surface truncated_chunk_ids)
- ~~Q8 Default rerank_tier~~ → D6 (feature flag enabled=False)
- ~~Q9 BudgetGuard interaction~~ → D7 (skip when remaining<min_budget; httpx timeout from remaining)
- ~~Q10 Cache invalidation on generation swap~~ → D3 (cache key generation-independent; no invalidation needed)

## Requirements

- Reranker is vendor-neutral at contract level; SF Qwen3-0.6B is one implementation.
- Existing `/retrieve` callers continue working unchanged.
- ACL respected: `allow_external_reranker=False` never makes external HTTP call.
- Failures degrade gracefully (vendor down → fallback noop → result + warning).
- Plan log captures rerank metadata.
- New tests cover Protocol, SF adapter (mocked HTTP), calibration, dispatcher, circuit breaker, ACL gate, plan log integration.

## Acceptance Criteria

- [ ] Eval slice named before `task.py start`.
- [ ] Reranker Protocol + RerankDoc / RerankResult defined.
- [ ] SF adapter implements Protocol; mocked HTTP tests cover happy path, retry, circuit breaker, truncation.
- [ ] Dispatcher routes per `Budget.rerank_tier` + `Budget.allow_external_reranker`.
- [ ] Calibration transforms raw scores before fusion.
- [ ] `/retrieve` integrates rerank stage; legacy callers unaffected.
- [ ] QueryPlan.rerank populated; plan log rerank_json written async.
- [ ] BudgetGuard interaction documented.
- [ ] Vendor failure does not raise; warnings appear in response.
- [ ] architecture.md A3 ✅; Settings reflects new module.
- [ ] No regression in existing 691-test suite.

## Out of Scope

- LLM-as-judge Tier-2 reranker.
- Offline teacher pipeline (Qwen3-Reranker-8B for distillation).
- Visual reranker (Qwen3-VL-Reranker-8B) — Phase 7B.
- BGE/BCE fallback adapter implementation.
- Postgres / persistent rerank cache.
- Adaptive top_n based on intent.
- Rerank in `/search` (legacy compat endpoint).

## Research References

- `.trellis/spec/backend/architecture.md` § A3
- archive: `.trellis/tasks/archive/2026-05/05-17-architecture-v2/prd.md`
- archive: `.trellis/tasks/archive/2026-05/05-18-queryplan-plan-log/`
- memory: [[architecture-v2-followup-roadmap]], [[arch-vendor-specifics-discipline]], [[t2-queryplan-mechanism-key-points]], [[t1-implementation-lessons]]

