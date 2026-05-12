# implement.md — M4 可观测性实施 checklist

> Principle: add observability as a thin layer around existing behavior. Do not rewrite search, rebuild, cache, or auth logic just to emit telemetry.

---

## Phase A — 配置与依赖

- [ ] **A1** `pyproject.toml` add dependencies:
  - `prometheus-client`
  - `opentelemetry-api`
  - `opentelemetry-sdk`
  - `opentelemetry-instrumentation-fastapi`
  - `opentelemetry-exporter-otlp`
- [ ] **A2** `src/tagmemorag/config.py` add:
  - `MetricsConfig`
  - `TracingConfig`
  - `ObservabilityConfig`
  - `Settings.observability`
- [ ] **A3** `config.yaml` add defaults:
  - metrics enabled at `/metrics`
  - tracing disabled
- [ ] **A4** Add `/metrics` to default `AuthConfig.public_paths`.
- [ ] **A5** Extend config env tests:
  - `TAGMEMORAG__OBSERVABILITY__METRICS__ENABLED=false`
  - `TAGMEMORAG__OBSERVABILITY__TRACING__SAMPLE_RATIO=0.25`

Validation:

```bash
uv run pytest tests/unit/test_config_env.py -v
```

---

## Phase B — Prometheus metrics foundation

- [ ] **B1** Create `src/tagmemorag/observability/__init__.py`.
- [ ] **B2** Create `src/tagmemorag/observability/metrics.py`.
- [ ] **B3** Implement metric singleton/registry helpers:
  - `configure_metrics(...)`
  - `get_metrics()`
  - `reset_metrics_for_tests()`
  - safe no-op fallback when disabled
- [ ] **B4** Define custom metrics with prefix `tagmemorag_`.
- [ ] **B5** Add helper methods:
  - `record_http_request`
  - `record_search`
  - `record_cache_operation`
  - `record_rate_limit`
  - `record_rebuild_started/done/failed/rejected`
  - `set_rebuild_in_progress`
  - `set_kbs_loaded`
  - `set_embedder_ready`
  - `record_embedding`
- [ ] **B6** Unit tests for metric registration and label constraints.

Validation:

```bash
uv run pytest tests/unit/test_observability_metrics.py -v
```

---

## Phase C — API metrics endpoint and HTTP middleware

- [ ] **C1** In `api.py` lifespan startup, configure metrics before serving requests.
- [ ] **C2** Mount official Prometheus ASGI app at `settings.observability.metrics.path`.
- [ ] **C3** Add HTTP metrics middleware:
  - skip `/metrics`
  - record route template / method / status code / duration
  - handle exception path as status `500`
- [ ] **C4** Verify `/metrics` remains public when auth is enabled.
- [ ] **C5** Tests:
  - `/metrics` returns text exposition
  - request counter increments after `/health` or `/search`
  - no auth required

Validation:

```bash
uv run pytest tests/unit/test_m4_api_observability.py -v
```

---

## Phase D — Search/cache/rate-limit/rebuild metrics

- [ ] **D1** Instrument `/search`:
  - cache hit/miss counter
  - search counter and latency
  - result count histogram
  - known error outcome
- [ ] **D2** Instrument embedding query latency and failures around `embedder.encode_query`.
- [ ] **D3** Instrument `/admin/cache/clear`.
- [ ] **D4** Instrument `auth.dependencies.rate_limit_dep` for allowed/limited outcomes.
- [ ] **D5** Instrument `state.start_rebuild` and `_rebuild_worker`:
  - accepted/rejected
  - in-progress gauge
  - done/failed
  - duration
- [ ] **D6** Instrument startup readiness gauges:
  - `tagmemorag_embedder_ready`
  - `tagmemorag_kbs_loaded`
- [ ] **D7** Tests for hit/miss, 429, rebuild accepted/rejected, and failed rebuild if cheap to trigger.

Validation:

```bash
uv run pytest tests/unit/test_cache.py tests/unit/test_rate_limit.py tests/unit/test_m4_api_observability.py -v
```

---

## Phase E — OpenTelemetry tracing

- [ ] **E1** Create `src/tagmemorag/observability/tracing.py`.
- [ ] **E2** Implement `configure_tracing(app, settings)`:
  - disabled => noop
  - resource `service.name`
  - parent-based trace id ratio sampler
  - OTLP exporter when endpoint is set
  - FastAPI instrumentation
  - idempotent guard
- [ ] **E3** Implement safe span helpers:
  - `start_span(name, **attrs)`
  - `set_span_attributes(**attrs)`
- [ ] **E4** Add business spans:
  - `tagmemorag.search`
  - `tagmemorag.search.cache`
  - `tagmemorag.search.embedding`
  - `tagmemorag.search.wave`
  - `tagmemorag.rebuild`
  - `tagmemorag.kb.load`
  - `tagmemorag.kb.build`
  - `tagmemorag.cache.clear`
- [ ] **E5** Add `tagmemorag.x_trace_id` attribute from existing request state.
- [ ] **E6** Tests:
  - disabled tracing does not require exporter
  - setup is idempotent
  - business span helper does not throw when no provider configured

Validation:

```bash
uv run pytest tests/unit/test_observability_tracing.py -v
```

---

## Phase F — Documentation and full validation

- [ ] **F1** README add Observability section:
  - `/metrics` curl
  - config and env examples
  - Prometheus scrape snippet
  - OTLP collector example
  - PromQL examples
- [ ] **F2** README explain privacy/cardinality rules.
- [ ] **F3** Update backend logging spec if M4 establishes reusable telemetry conventions.
- [ ] **F4** Run full tests.
- [ ] **F5** Manual smoke:

```bash
uv run python -m tagmemorag build --docs tests/fixtures --kb default --config config.yaml
uv run python -m tagmemorag serve --host 127.0.0.1 --port 8000 --config config.yaml
curl http://127.0.0.1:8000/metrics | grep tagmemorag
curl http://127.0.0.1:8000/health
```

Validation:

```bash
uv run pytest tests/ -v
```

---

## Review Gates

- [ ] Metrics labels reviewed for cardinality and privacy.
- [ ] `/metrics` auth/public-path behavior verified.
- [ ] Tracing disabled path verified with no collector.
- [ ] Existing response shapes unchanged.
- [ ] Full regression green.

---

## Rollback Points

- Phase B fails: keep config only, remove metrics mount.
- Phase D causes behavior risk: keep HTTP metrics, defer business metrics.
- Phase E causes dependency/runtime risk: disable tracing by default and ship metrics-only M4.
- Documentation can ship after metrics if code is already validated, but final task is not done until README is updated.

---

## Out of Scope

- Grafana dashboard and alerts.
- K8s ServiceMonitor/PodMonitor.
- Per-API-key metrics labels.
- Storing traces or metrics inside TagMemoRAG.
- Eval quality trend reporting.
