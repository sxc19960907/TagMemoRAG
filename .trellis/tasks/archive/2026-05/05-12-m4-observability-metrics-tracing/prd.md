# brainstorm: M4 可观测性（Prometheus Metrics + OpenTelemetry Traces）

## Goal

在 M0-M3 的检索、运维、安全、多 KB、缓存和 eval 基础上，补齐生产排障与容量观察能力：暴露 Prometheus `/metrics`，接入 OpenTelemetry trace，并让 search / rebuild / cache / rate limit / embedding / KB readiness 的关键运行状态可被指标和 trace 关联起来。完成后，运维可以回答“慢在哪里、错在哪里、哪个 KB/调用方受影响、缓存和限流是否生效”。

## Background / Known Context

- M1 已交付 structlog JSON 日志、`X-Trace-Id`、`/health`、`/ready`、graceful shutdown 和模型 warm-up。
- M2 已交付 API key、per-key rate limit、多 KB、查询缓存；日志里已有 `api_key_id`、`kb_name`、`cache_status` 等字段基础。
- M3 已交付离线 eval gate；M4 不替代质量 eval，而是观察线上运行时行为。
- 当前 `api.py` 已有 search/cache/rebuild 日志，但没有 Prometheus registry、`/metrics` 或 OpenTelemetry provider/instrumentation。
- 当前配置使用 Pydantic Settings + `TAGMEMORAG__` env 覆盖；M4 应继续沿用该模式。
- 项目依赖已有 FastAPI、Uvicorn、structlog；M4 可以新增轻量官方观测依赖。
- M1 文档已把 Prometheus `/metrics` 和 OTel traces 明确列为 M4 范围。

## Assumptions (temporary)

- 首版部署仍以单进程/单 Pod 为主；多副本聚合交给 Prometheus 后端。
- Prometheus scrape `/metrics` 不需要 API key 鉴权，但路径应进入 auth public paths 默认值，避免生产启用 auth 后抓取失败。
- Trace 默认可关闭；未配置 exporter 时不应影响服务启动或请求成功。
- 不把原始 query、文档 chunk、API key、embedding vector 写入 metrics labels、trace attributes 或 logs。
- M4 目标是“可排障的基础仪表”，不是完整 SRE 平台。

## Decision (ADR-lite)

### Decision: Metrics 暴露方式 = `prometheus_client` 官方 ASGI app

**Context**：候选方案包括直接使用官方 `prometheus_client`、引入 `prometheus-fastapi-instrumentator` 或自己手写 text exposition。

**Decision**：
- 使用官方 `prometheus_client`，通过 `make_asgi_app()` 挂载 `/metrics`。
- 项目自定义业务指标在 `src/tagmemorag/observability/metrics.py` 定义，并通过小型 helper 记录。
- 不使用额外 FastAPI metrics 框架作为 M4 默认路径。

**Rationale**：
- 官方库依赖少、长期稳定，适合当前小型服务。
- 自定义业务指标比通用 HTTP 指标更重要：search latency、cache hit/miss、rebuild status、embedding latency、KB loaded count。
- 避免第三方自动框架带来的标签爆炸或默认指标不可控。

**Consequences**：
- 新依赖：`prometheus-client`。
- `/metrics` 返回 Prometheus text exposition。
- 需要测试指标注册幂等性，避免 TestClient 多次导入时报 duplicated timeseries。

### Decision: Trace 接入 = OTel FastAPI instrumentation + 关键业务手动 span

**Context**：只用自动 FastAPI instrumentation 能看到 HTTP 边界，但看不到 embedding、wave_search、cache、rebuild 等业务阶段；全手写 span 又容易遗漏通用 HTTP 信息。

**Decision**：
- 使用 OpenTelemetry 官方 Python SDK + FastAPI instrumentation。
- 在业务关键点补手动 span：
  - `search.cache`
  - `search.embedding`
  - `search.wave`
  - `rebuild.build`
  - `kb.load`
  - `cache.clear`
- 采样率可配，默认关闭或无 exporter noop；生产通过 OTLP exporter 打到 collector。

**Rationale**：
- 自动 HTTP span + 手动业务 span 兼顾覆盖面和诊断价值。
- OTel 是标准化路径，后续接 Jaeger/Tempo/OTel Collector 不改业务代码。
- 保留现有 `X-Trace-Id` 作为响应与日志关联 ID；OTel `trace_id` 作为分布式追踪 ID，两者在 span attributes/log context 中互相绑定。

**Consequences**：
- 新依赖候选：
  - `opentelemetry-api`
  - `opentelemetry-sdk`
  - `opentelemetry-instrumentation-fastapi`
  - `opentelemetry-exporter-otlp`
- 新配置段 `observability.tracing.*`。
- 未配置 exporter 时请求不能失败；trace 初始化异常应 log warning 并降级 noop。

### Decision: Label 策略 = 低基数、业务可定位

**Context**：Prometheus labels 一旦使用 query text、trace id、task id、build id 等高基数字段，会导致存储和查询成本失控。

**Decision**：
- 允许 label：
  - `route`
  - `method`
  - `status_code`
  - `kb_name`
  - `cache_status`
  - `error_code`
  - `operation`
  - `outcome`
- 禁止 label：
  - raw `question`
  - `trace_id`
  - `task_id`
  - API key plaintext 或 hash
  - full `build_id`
  - source file path / document text
- 对 `api_key_id`：M4 默认不作为 metrics label；可以进入 trace attribute/log field。若未来需要 per-client metrics，再加可配置 allowlist 或 hashed bucket。

**Rationale**：
- 指标用于聚合观察，trace/log 用于单请求定位。
- `kb_name` 基数在 M2 假设中 <50，可接受。
- `api_key_id` 调用方数量虽小，但默认加入 labels 容易让部署方养成坏习惯；先保守。

### Decision: M4 不做 Dashboard/Alert 全套，只提供指标契约和示例查询

**Decision**：
- README 增加 `/metrics`、OTel 配置和 PromQL 示例。
- 不新增 Grafana dashboard JSON、Alertmanager 规则、K8s ServiceMonitor。
- 这些留到后续 ops packaging 任务。

## Requirements

### 1. Prometheus Metrics

- 暴露 `GET /metrics`，默认启用，且不要求 API key。
- 支持通过配置关闭 metrics 暴露。
- 提供 HTTP 请求计数和延迟指标：
  - route / method / status_code
  - 不记录 `/metrics` 自身，或至少避免把 scrape 噪音计入业务请求指标。
- 提供 search 指标：
  - search 总次数，按 `kb_name / cache_status / outcome`
  - search latency histogram
  - result count histogram 或 summary
- 提供 cache 指标：
  - cache hit/miss counter
  - cache clear counter
  - current cache entries gauge（如果实现成本低）
- 提供 rate limit 指标：
  - allowed/limited counter，按 `outcome`
  - 429 response 可通过 HTTP/status 指标看到。
- 提供 rebuild 指标：
  - rebuild started/done/failed/rejected counter
  - rebuild duration histogram
  - rebuild in-progress gauge
- 提供 startup/readiness 指标：
  - service startup duration
  - KB loaded gauge
  - embedder ready gauge
- 提供 embedding 指标：
  - encode query/batch latency histogram
  - failures counter

### 2. OpenTelemetry Tracing

- 支持配置启用/关闭 tracing。
- 支持 OTLP endpoint 配置。
- 自动为 FastAPI HTTP 请求创建 span。
- 手动 span 覆盖 search/cache/embedding/wave/rebuild/load/cache clear。
- Span attributes 使用低敏字段：
  - `tagmemorag.kb_name`
  - `tagmemorag.cache_status`
  - `tagmemorag.build_id`（可选；只在 trace，不在 metric label）
  - `tagmemorag.query_len`
  - `tagmemorag.result_count`
  - `tagmemorag.error_code`
  - `tagmemorag.x_trace_id`
- OTel 失败或 exporter 不可用不能影响 API 成功路径。

### 3. Config and Runtime

- 新增 `ObservabilityConfig`，沿用 `TAGMEMORAG__OBSERVABILITY__...` env 覆盖。
- 默认配置偏开发友好：
  - metrics enabled
  - tracing disabled
  - no external exporter required
- README 和 `config.yaml` 记录默认值。
- 测试环境可以隔离 registry/tracer，避免跨测试污染。

### 4. Privacy and Cardinality

- 不把原始 query、文档文本、API key plaintext/hash、embedding vectors 放入 metrics/traces。
- Metrics labels 必须在设计文档中列清楚。
- 每个新增 label 都要有“为什么基数可控”的说明。

### 5. Documentation

- README 增加 Observability 章节：
  - `/metrics` curl 示例
  - 推荐 Prometheus scrape snippet
  - OTLP/Collector env 示例
  - 3-5 条 PromQL 示例
- 说明如何把 `X-Trace-Id`、日志字段和 OTel trace 关联。

## Acceptance Criteria

- [ ] `GET /metrics` 返回 Prometheus text exposition，包含 Python runtime 指标和 TagMemoRAG 自定义指标。
- [ ] `/metrics` 在 auth enabled 时仍可被访问，除非配置显式移除 public path。
- [ ] `/search` cache miss/hit 分别更新 search/cache 指标。
- [ ] `/search` 出错时更新 error/outcome 指标，且原 structured error response 不变。
- [ ] `/rebuild` started/done/failed/rejected 都有指标覆盖。
- [ ] Rate limit allowed/limited 有指标或可由 HTTP 指标可靠表达，429 有 `error_code=RATE_LIMITED` 维度。
- [ ] 启用 tracing 后，TestClient 请求能产生 FastAPI span 和业务 span；关闭 tracing 时无外部依赖要求。
- [ ] 指标 labels 不包含 query、trace_id、API key、task_id、full source path。
- [ ] `uv run pytest tests/ -v` 全绿。
- [ ] README 和 `config.yaml` 覆盖 M4 配置和使用说明。

## Definition of Done

- PRD、design、implement 文档完成并经确认。
- 新增/更新测试覆盖 metrics endpoint、指标变化、tracing 初始化、隐私/低基数约束。
- 现有 M0-M3 行为无破坏：build/search/API/auth/rate-limit/cache/eval 测试保持绿。
- 新依赖必要且记录清楚。
- M4 不引入 dashboard/alerting 平台耦合。

## Out of Scope (explicit)

- Grafana dashboard JSON。
- Alertmanager / PrometheusRule / ServiceMonitor manifests。
- 分布式多副本 rebuild 协调。
- Redis-backed metrics/cache/rate-limit。
- Per-user 或 per-api-key Prometheus labels。
- LLM quality metrics、eval result long-term tracking（M3/M5 后续）。
- Full query capture、PII 检测或审计检索内容存档。

## Research References

- [research/observability-options.md](./research/observability-options.md)
- M1 logging/health foundation: `.trellis/tasks/archive/2026-05/05-11-m1-ops-foundation/`
- M2 auth/rate-limit/cache foundation: `.trellis/tasks/05-12-m2-security-multikb-cache/`
- Backend logging spec: `.trellis/spec/backend/logging-guidelines.md`
