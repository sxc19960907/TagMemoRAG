# design.md — M4 可观测性技术设计

> Scope: Prometheus metrics + OpenTelemetry traces for the existing FastAPI service. Dashboards, alert rules, and multi-replica coordination are out of scope.
> Parent: [prd.md](./prd.md)

---

## 1. Module Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│ FastAPI app (api.py)                                        │
│                                                             │
│  middleware: trace_id → http metrics → auth/rate limit      │
│  mounted app: /metrics                                      │
│  handlers: search / rebuild / anchor / kb / cache clear     │
│       │                                                     │
│       ├── observability.metrics record_* helpers            │
│       └── observability.tracing span helpers                │
└─────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ state.py                                                    │
│  build_kb / load_kb / start_rebuild / _rebuild_worker       │
│       │                                                     │
│       ├── rebuild counters + gauges                         │
│       ├── rebuild duration histogram                        │
│       └── build/load spans                                  │
└─────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ observability package                                       │
│  metrics.py: Prometheus registry, metric definitions         │
│  tracing.py: OTel setup, tracer access, safe span helpers    │
└─────────────────────────────────────────────────────────────┘
```

### File Changes

| File | Type | Summary |
|------|------|---------|
| `pyproject.toml` | edit | Add Prometheus + OTel dependencies |
| `src/tagmemorag/config.py` | edit | Add `ObservabilityConfig` |
| `src/tagmemorag/observability/__init__.py` | new | Package exports |
| `src/tagmemorag/observability/metrics.py` | new | Metric definitions + helpers |
| `src/tagmemorag/observability/tracing.py` | new | OTel initialization + span helpers |
| `src/tagmemorag/api.py` | edit | Mount `/metrics`, HTTP metrics middleware, search/cache spans |
| `src/tagmemorag/state.py` | edit | Rebuild/build/load metrics and spans |
| `config.yaml` | edit | Add observability defaults |
| `README.md` | edit | Observability usage |
| `tests/unit/test_observability_metrics.py` | new | Metrics endpoint and counters |
| `tests/unit/test_observability_tracing.py` | new | Tracing setup/noop behavior |
| `tests/unit/test_m4_api_observability.py` | new | API-level instrumentation behavior |

---

## 2. Configuration Contract

```python
class MetricsConfig(BaseModel):
    enabled: bool = True
    path: str = "/metrics"
    include_runtime: bool = True

class TracingConfig(BaseModel):
    enabled: bool = False
    service_name: str = "tagmemorag"
    otlp_endpoint: str | None = None
    sample_ratio: float = 1.0
    export_timeout_seconds: float = 5.0

class ObservabilityConfig(BaseModel):
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    tracing: TracingConfig = Field(default_factory=TracingConfig)
```

Add to `Settings`:

```python
observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
```

Environment examples:

```text
TAGMEMORAG__OBSERVABILITY__METRICS__ENABLED=true
TAGMEMORAG__OBSERVABILITY__METRICS__PATH=/metrics
TAGMEMORAG__OBSERVABILITY__TRACING__ENABLED=true
TAGMEMORAG__OBSERVABILITY__TRACING__OTLP_ENDPOINT=http://otel-collector:4317
TAGMEMORAG__OBSERVABILITY__TRACING__SAMPLE_RATIO=0.1
```

Compatibility:

- Metrics are enabled by default because `/metrics` is passive and local scrape friendly.
- Tracing is disabled by default to avoid requiring an external collector.
- Add `/metrics` to `auth.public_paths` default and `config.yaml`; if an operator removes it, auth behavior follows config.

---

## 3. Metrics Design

### 3.1 Registry Strategy

Use a local registry wrapper to avoid duplicated timeseries during tests:

```python
def create_metrics(registry: CollectorRegistry | None = None) -> Metrics:
    ...

def get_metrics() -> Metrics:
    ...

def reset_metrics_for_tests() -> None:
    ...
```

Production can use the default registry so Python runtime/process metrics remain visible. Unit tests can reset the module-level singleton or use a dedicated registry.

### 3.2 Metric Names

All custom metrics use prefix `tagmemorag_`.

| Name | Type | Labels | Purpose |
|------|------|--------|---------|
| `tagmemorag_http_requests_total` | Counter | `method`, `route`, `status_code` | HTTP request volume |
| `tagmemorag_http_request_duration_seconds` | Histogram | `method`, `route` | HTTP latency |
| `tagmemorag_search_requests_total` | Counter | `kb_name`, `cache_status`, `outcome`, `error_code` | Search volume and failures |
| `tagmemorag_search_duration_seconds` | Histogram | `kb_name`, `cache_status`, `outcome` | Search latency |
| `tagmemorag_search_results_count` | Histogram | `kb_name` | Result counts |
| `tagmemorag_cache_operations_total` | Counter | `operation`, `outcome` | get hit/miss, set, clear |
| `tagmemorag_cache_entries` | Gauge | none | Current in-memory cache size if cheap |
| `tagmemorag_rate_limit_checks_total` | Counter | `outcome` | allowed vs limited |
| `tagmemorag_rebuilds_total` | Counter | `kb_name`, `outcome` | started/done/failed/rejected |
| `tagmemorag_rebuild_duration_seconds` | Histogram | `kb_name`, `outcome` | Rebuild worker duration |
| `tagmemorag_rebuilds_in_progress` | Gauge | `kb_name` | Active rebuilds |
| `tagmemorag_kbs_loaded` | Gauge | none | Loaded KB count |
| `tagmemorag_embedder_ready` | Gauge | none | 0/1 readiness |
| `tagmemorag_embedding_duration_seconds` | Histogram | `operation`, `outcome` | encode query/batch latency |
| `tagmemorag_embedding_failures_total` | Counter | `operation` | Embedding failures |

### 3.3 Label Rules

Allowed:

- `method`: finite HTTP method set.
- `route`: route template such as `/search`, not raw URL path.
- `status_code`: finite HTTP status codes.
- `kb_name`: expected <50 in M2 assumptions.
- `cache_status`: `hit`, `miss`, `disabled`, `none`.
- `outcome`: `success`, `error`, `limited`, `rejected`, `started`, `done`, `failed`.
- `error_code`: project `ErrorCode` or `none`.
- `operation`: finite internal operation names.

Forbidden:

- raw query text
- trace id
- task id
- API key plaintext/hash
- raw source path
- embedding vectors
- unbounded exception messages

### 3.4 HTTP Middleware

Add middleware after trace ID middleware:

```python
@app.middleware("http")
async def metrics_middleware(request, call_next):
    if request.url.path == settings.observability.metrics.path:
        return await call_next(request)
    route = _route_template(request)
    t0 = time.perf_counter()
    status_code = "500"
    try:
        response = await call_next(request)
        status_code = str(response.status_code)
        return response
    finally:
        metrics.record_http_request(method=request.method, route=route, status_code=status_code, duration=...)
```

`_route_template` should prefer `request.scope["route"].path` after routing when available, falling back to `request.url.path`.

---

## 4. Tracing Design

### 4.1 Initialization

`observability/tracing.py`:

```python
def configure_tracing(app: FastAPI, cfg: Settings) -> None:
    if not cfg.observability.tracing.enabled:
        return
    # Resource(service.name), sampler, OTLP exporter if endpoint is set
    # FastAPIInstrumentor.instrument_app(app)
```

Requirements:

- Idempotent across tests and repeated lifespan startup.
- Fail closed to noop: initialization errors log warning and do not crash service.
- Do not double-instrument the app.

### 4.2 Span Helpers

```python
@contextmanager
def start_span(name: str, **attrs):
    ...

def set_span_attributes(**attrs) -> None:
    ...
```

The helper sanitizes attributes:

- Convert values to str/int/float/bool where possible.
- Drop `None`.
- Never accept raw query or secret fields by helper contract.

### 4.3 Span Names

| Span | Location |
|------|----------|
| `tagmemorag.search` | `api.search` wrapper |
| `tagmemorag.search.cache` | cache lookup |
| `tagmemorag.search.embedding` | query embedding |
| `tagmemorag.search.wave` | WAVE propagation |
| `tagmemorag.rebuild` | rebuild worker |
| `tagmemorag.kb.load` | KB load during startup |
| `tagmemorag.kb.build` | `build_kb` |
| `tagmemorag.cache.clear` | admin clear endpoint |

### 4.4 Attribute Contract

Use `tagmemorag.*` names:

```text
tagmemorag.kb_name
tagmemorag.build_id
tagmemorag.cache_status
tagmemorag.query_len
tagmemorag.top_k
tagmemorag.result_count
tagmemorag.error_code
tagmemorag.x_trace_id
tagmemorag.rebuild.task_status
```

Trace can include `build_id` and `x_trace_id`; metrics cannot.

---

## 5. Instrumentation Points

### `/search`

Flow:

1. `tagmemorag.search` span starts after auth/kb access passes.
2. Cache lookup span records hit/miss.
3. Cache hit:
   - record `search_requests_total{cache_status="hit", outcome="success"}`
   - record latency and result count
4. Cache miss:
   - span `search.embedding`
   - record embedding duration/failure
   - span `search.wave`
   - record search metrics
5. Known `ServiceError`:
   - record search `outcome="error", error_code=<code>`
   - preserve existing error response.

### `/rebuild`

At request acceptance:

- started counter if accepted.
- rejected counter for same-KB conflict or shutdown.
- in-progress gauge increments only for accepted worker.

In worker:

- done/failed counter.
- duration histogram.
- in-progress gauge decrements in finally.
- `tagmemorag.rebuild` span around build/save/swap.

### Startup / KB Load

- `service_startup_duration_seconds` can be optional; existing `service_ready` log already has `startup_duration_ms`.
- `kbs_loaded` set after `_load_all_kbs`.
- `embedder_ready` set to 1 after warmup.
- KB load spans wrap each `load_kb` call.

### Rate Limit

Best location is `auth.dependencies.rate_limit_dep`, where outcome is known. If avoiding cross-module import cycles, expose a tiny metrics helper and import it there.

### Cache

Record `get` hit/miss in `api.search` so `kb_name` and cache status are already known. Record `clear` in `/admin/cache/clear`.

---

## 6. Error Handling

- Metrics recording must never raise into request flow.
- Tracing setup failure logs `observability_tracing_init_failed`.
- Metrics setup failure is more serious but should still be testable; if `/metrics` mount fails due to config error, startup should log error and continue without metrics only if `metrics.enabled=false`. Otherwise fail fast is acceptable because misconfigured observability should be obvious.
- Known `ServiceError` format remains `{code, message, detail}`.

---

## 7. Tests

Unit:

- `test_metrics_endpoint_exposes_custom_metrics`
- `test_search_cache_hit_and_miss_increment_metrics`
- `test_metrics_do_not_include_query_or_trace_id_labels`
- `test_rate_limit_records_limited_outcome`
- `test_rebuild_metrics_started_done_failed_rejected`
- `test_tracing_disabled_is_noop`
- `test_tracing_configure_is_idempotent`

Integration-ish:

- TestClient with auth enabled can access `/metrics` without token.
- Search request still returns `X-Trace-Id` and search response unchanged.
- Full suite still passes.

---

## 8. Rollout / Rollback

Rollout:

1. Deploy with metrics enabled, tracing disabled.
2. Add Prometheus scrape for `/metrics`.
3. Watch metric cardinality and scrape size.
4. Enable tracing in staging with OTLP collector.
5. Enable production sampling at low ratio, e.g. 0.01-0.1.

Rollback:

- Set `TAGMEMORAG__OBSERVABILITY__METRICS__ENABLED=false` to remove metrics mount on restart.
- Set `TAGMEMORAG__OBSERVABILITY__TRACING__ENABLED=false` to disable tracing.
- If dependencies cause packaging issues, remove only `observability/tracing.py` integration first; metrics can remain independent.

---

## 9. Deferred

- Grafana dashboard.
- Alerting rules.
- ServiceMonitor / PodMonitor manifests.
- Per-client Prometheus labels.
- HTTP eval traces.
- Cross-pod rebuild/queue metrics.
