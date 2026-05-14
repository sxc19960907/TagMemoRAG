from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, REGISTRY, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST, make_asgi_app


ALLOWED_LABEL_NAMES = {
    "method",
    "route",
    "status_code",
    "kb_name",
    "cache_status",
    "error_code",
    "operation",
    "outcome",
}
FORBIDDEN_LABEL_NAMES = {"question", "query", "trace_id", "task_id", "api_key", "api_key_id", "build_id", "path"}


@dataclass
class MetricsConfig:
    enabled: bool = True
    include_runtime: bool = True


class NoopMetrics:
    enabled = False

    def __getattr__(self, name: str):
        if name.startswith(("record_", "set_")):
            return lambda *args, **kwargs: None
        raise AttributeError(name)


class Metrics:
    SEARCH_BUCKETS: ClassVar[tuple[float, ...]] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
    RESULT_BUCKETS: ClassVar[tuple[float, ...]] = (0, 1, 2, 3, 5, 8, 13, 21, 34, 55)

    def __init__(self, registry: CollectorRegistry, *, enabled: bool = True) -> None:
        self.registry = registry
        self.enabled = enabled
        self.http_requests = Counter(
            "tagmemorag_http_requests_total",
            "HTTP request volume.",
            ["method", "route", "status_code"],
            registry=registry,
        )
        self.http_duration = Histogram(
            "tagmemorag_http_request_duration_seconds",
            "HTTP request latency.",
            ["method", "route"],
            registry=registry,
            buckets=self.SEARCH_BUCKETS,
        )
        self.http_errors = Counter(
            "tagmemorag_http_errors_total",
            "HTTP error volume by route, status, and stable error code.",
            ["route", "status_code", "error_code"],
            registry=registry,
        )
        self.search_requests = Counter(
            "tagmemorag_search_requests_total",
            "Search request volume by KB, cache status, and outcome.",
            ["kb_name", "cache_status", "outcome", "error_code"],
            registry=registry,
        )
        self.search_duration = Histogram(
            "tagmemorag_search_duration_seconds",
            "Search latency by KB and cache status.",
            ["kb_name", "cache_status", "outcome"],
            registry=registry,
            buckets=self.SEARCH_BUCKETS,
        )
        self.search_results = Histogram(
            "tagmemorag_search_results_count",
            "Search result count.",
            ["kb_name"],
            registry=registry,
            buckets=self.RESULT_BUCKETS,
        )
        self.cache_operations = Counter(
            "tagmemorag_cache_operations_total",
            "Cache operation volume.",
            ["operation", "outcome"],
            registry=registry,
        )
        self.cache_entries = Gauge("tagmemorag_cache_entries", "Current query cache entry count.", registry=registry)
        self.rate_limit_checks = Counter(
            "tagmemorag_rate_limit_checks_total",
            "Rate limit decisions.",
            ["outcome"],
            registry=registry,
        )
        self.rebuilds = Counter(
            "tagmemorag_rebuilds_total",
            "Rebuild lifecycle events.",
            ["kb_name", "outcome"],
            registry=registry,
        )
        self.rebuild_duration = Histogram(
            "tagmemorag_rebuild_duration_seconds",
            "Rebuild worker duration.",
            ["kb_name", "outcome"],
            registry=registry,
            buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0),
        )
        self.rebuilds_in_progress = Gauge(
            "tagmemorag_rebuilds_in_progress",
            "Active rebuilds.",
            ["kb_name"],
            registry=registry,
        )
        self.kbs_loaded = Gauge("tagmemorag_kbs_loaded", "Loaded knowledge base count.", registry=registry)
        self.embedder_ready = Gauge("tagmemorag_embedder_ready", "Whether the embedder is warmed up.", registry=registry)
        self.startup_duration = Gauge(
            "tagmemorag_startup_duration_seconds",
            "Most recent service startup duration.",
            registry=registry,
        )
        self.embedding_duration = Histogram(
            "tagmemorag_embedding_duration_seconds",
            "Embedding encode latency.",
            ["operation", "outcome"],
            registry=registry,
            buckets=self.SEARCH_BUCKETS,
        )
        self.embedding_failures = Counter(
            "tagmemorag_embedding_failures_total",
            "Embedding encode failures.",
            ["operation"],
            registry=registry,
        )
        self.tag_embeddings = Counter(
            "tagmemorag_tag_embeddings_total",
            "Tag embedding operations by KB and outcome (added|skipped|failed).",
            ["kb_name", "outcome"],
            registry=registry,
        )
        self.tags_total = Gauge(
            "tagmemorag_tags_total",
            "Canonical tag count by KB.",
            ["kb_name"],
            registry=registry,
        )
        self.epa_basis_retrain = Counter(
            "tagmemorag_epa_basis_retrain_total",
            "EPA basis retrain events by outcome (cold-start|real-pca|skipped|failed).",
            ["outcome"],
            registry=registry,
        )
        self.epa_basis_retrain_duration = Histogram(
            "tagmemorag_epa_basis_retrain_duration_seconds",
            "EPA basis retrain duration.",
            ["outcome"],
            registry=registry,
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
        )

    def record_http_request(self, *, method: str, route: str, status_code: str | int, duration: float) -> None:
        self.http_requests.labels(method=method, route=route, status_code=str(status_code)).inc()
        self.http_duration.labels(method=method, route=route).observe(max(duration, 0.0))

    def record_http_error(self, *, route: str, status_code: str | int, error_code: str) -> None:
        self.http_errors.labels(route=route, status_code=str(status_code), error_code=error_code).inc()

    def record_search(
        self,
        *,
        kb_name: str,
        cache_status: str,
        outcome: str,
        duration: float,
        result_count: int = 0,
        error_code: str = "none",
    ) -> None:
        self.search_requests.labels(
            kb_name=kb_name,
            cache_status=cache_status,
            outcome=outcome,
            error_code=error_code,
        ).inc()
        self.search_duration.labels(kb_name=kb_name, cache_status=cache_status, outcome=outcome).observe(
            max(duration, 0.0)
        )
        if outcome == "success":
            self.search_results.labels(kb_name=kb_name).observe(max(int(result_count), 0))

    def record_cache_operation(self, *, operation: str, outcome: str) -> None:
        self.cache_operations.labels(operation=operation, outcome=outcome).inc()

    def set_cache_entries(self, count: int) -> None:
        self.cache_entries.set(max(int(count), 0))

    def record_rate_limit(self, *, outcome: str) -> None:
        self.rate_limit_checks.labels(outcome=outcome).inc()

    def record_rebuild_started(self, *, kb_name: str) -> None:
        self.rebuilds.labels(kb_name=kb_name, outcome="started").inc()

    def record_rebuild_done(self, *, kb_name: str, duration: float) -> None:
        self.rebuilds.labels(kb_name=kb_name, outcome="done").inc()
        self.rebuild_duration.labels(kb_name=kb_name, outcome="done").observe(max(duration, 0.0))

    def record_rebuild_failed(self, *, kb_name: str, duration: float) -> None:
        self.rebuilds.labels(kb_name=kb_name, outcome="failed").inc()
        self.rebuild_duration.labels(kb_name=kb_name, outcome="failed").observe(max(duration, 0.0))

    def record_rebuild_rejected(self, *, kb_name: str) -> None:
        self.rebuilds.labels(kb_name=kb_name, outcome="rejected").inc()

    def set_rebuild_in_progress(self, *, kb_name: str, value: int) -> None:
        self.rebuilds_in_progress.labels(kb_name=kb_name).set(max(int(value), 0))

    def set_kbs_loaded(self, count: int) -> None:
        self.kbs_loaded.set(max(int(count), 0))

    def set_embedder_ready(self, ready: bool) -> None:
        self.embedder_ready.set(1 if ready else 0)

    def record_startup_duration(self, duration: float) -> None:
        self.startup_duration.set(max(duration, 0.0))

    def record_embedding(self, *, operation: str, outcome: str, duration: float) -> None:
        self.embedding_duration.labels(operation=operation, outcome=outcome).observe(max(duration, 0.0))
        if outcome != "success":
            self.embedding_failures.labels(operation=operation).inc()

    def record_tag_embeddings(self, *, kb_name: str, outcome: str, count: int = 1) -> None:
        if count <= 0:
            return
        self.tag_embeddings.labels(kb_name=kb_name, outcome=outcome).inc(int(count))

    def set_tags_total(self, *, kb_name: str, count: int) -> None:
        self.tags_total.labels(kb_name=kb_name).set(max(int(count), 0))

    def record_epa_basis_retrain(self, *, outcome: str, duration: float) -> None:
        self.epa_basis_retrain.labels(outcome=outcome).inc()
        self.epa_basis_retrain_duration.labels(outcome=outcome).observe(max(duration, 0.0))


_metrics: Metrics | NoopMetrics = NoopMetrics()
_registry: CollectorRegistry = REGISTRY
_configured_key: tuple[bool, bool] | None = None


def create_metrics(registry: CollectorRegistry | None = None, *, enabled: bool = True) -> Metrics | NoopMetrics:
    if not enabled:
        return NoopMetrics()
    return Metrics(registry or REGISTRY)


def configure_metrics(*, enabled: bool = True, include_runtime: bool = True) -> Metrics | NoopMetrics:
    global _configured_key, _metrics, _registry
    key = (enabled, include_runtime)
    if _configured_key == key:
        return _metrics
    if not enabled:
        _registry = CollectorRegistry(auto_describe=True)
        _metrics = NoopMetrics()
        _configured_key = key
        return _metrics
    _registry = REGISTRY if include_runtime else CollectorRegistry(auto_describe=True)
    try:
        _metrics = Metrics(_registry, enabled=True)
    except ValueError:
        if include_runtime:
            _metrics = _metrics if isinstance(_metrics, Metrics) else NoopMetrics()
        else:
            raise
    _configured_key = key
    return _metrics


def get_metrics() -> Metrics | NoopMetrics:
    return _metrics


def get_registry() -> CollectorRegistry:
    return _registry


def make_metrics_app():
    return make_asgi_app(registry=_registry)


def metrics_response_bytes() -> tuple[bytes, str]:
    return generate_latest(_registry), CONTENT_TYPE_LATEST


def reset_metrics_for_tests(*, include_runtime: bool = False, enabled: bool = True) -> Metrics | NoopMetrics:
    global _configured_key, _metrics, _registry
    _configured_key = None
    _registry = CollectorRegistry(auto_describe=True) if not include_runtime else REGISTRY
    if enabled:
        _metrics = Metrics(_registry, enabled=True)
    else:
        _metrics = NoopMetrics()
    return _metrics


def assert_label_contract() -> None:
    used = {
        "method",
        "route",
        "status_code",
        "kb_name",
        "cache_status",
        "error_code",
        "operation",
        "outcome",
    }
    forbidden_used = used & FORBIDDEN_LABEL_NAMES
    if forbidden_used:
        raise AssertionError(f"Forbidden metric labels used: {sorted(forbidden_used)}")
    unknown = used - ALLOWED_LABEL_NAMES
    if unknown:
        raise AssertionError(f"Unknown metric labels used: {sorted(unknown)}")
