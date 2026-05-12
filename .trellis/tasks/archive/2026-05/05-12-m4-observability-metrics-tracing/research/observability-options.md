# Research: M4 Observability Options

## Sources

- Prometheus Python client documentation: https://prometheus.github.io/client_python/
- Prometheus Python ASGI exporter documentation: https://prometheus.github.io/client_python/exporting/http/asgi/
- OpenTelemetry Python documentation: https://opentelemetry.io/docs/languages/python/
- OpenTelemetry Python instrumentation documentation: https://opentelemetry.io/docs/zero-code/python/
- OpenTelemetry FastAPI instrumentation package docs: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html

## Findings

### Prometheus

The official Python client supports counters, gauges, summaries, histograms, and an ASGI exporter. Because TagMemoRAG is already FastAPI/ASGI, mounting the official ASGI app at `/metrics` is the smallest and most controlled implementation.

Using a FastAPI-specific third-party instrumentator could reduce boilerplate for HTTP metrics, but M4 needs custom domain metrics more than generic request metrics. A thin local observability module keeps labels explicit and avoids accidental high-cardinality defaults.

Recommendation: use `prometheus-client` directly.

### OpenTelemetry

OpenTelemetry Python supports automatic instrumentation and manual spans. FastAPI instrumentation covers request-level spans, while custom spans are still needed for the important TagMemoRAG stages: cache lookup, query embedding, WAVE propagation, rebuild, KB loading, and cache clear.

Recommendation: use FastAPI instrumentation for HTTP spans, plus local helper functions/context managers for business spans. Keep tracing disabled by default and initialize a noop tracer if the exporter is not configured.

### Cardinality and Privacy

Metrics labels should stay low-cardinality. `kb_name`, `route`, `method`, `status_code`, `cache_status`, `error_code`, `operation`, and `outcome` are acceptable in M4. Query text, trace IDs, API keys, task IDs, source paths, and embedding vectors must not appear in metrics labels.

Trace attributes can be richer than metrics labels, but should still avoid secrets and raw content. Use `query_len` rather than query text, and bind the existing `X-Trace-Id` as an attribute so logs, responses, and traces can be correlated.

## Chosen Approach

1. Add `src/tagmemorag/observability/metrics.py` for metric definitions and recording helpers.
2. Add `src/tagmemorag/observability/tracing.py` for OTel setup and span helpers.
3. Mount `/metrics` in `api.py` when enabled.
4. Instrument existing boundary points rather than rewriting algorithms.
5. Keep dashboards and alerting manifests out of M4.
