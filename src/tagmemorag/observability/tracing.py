from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
import structlog


_instrumented_apps: set[int] = set()
_configured = False


def configure_tracing(app: FastAPI, settings) -> None:
    global _configured
    cfg = settings.observability.tracing
    if not cfg.enabled:
        return
    try:
        if not _configured:
            provider = TracerProvider(
                resource=Resource.create({"service.name": cfg.service_name}),
                sampler=ParentBased(TraceIdRatioBased(cfg.sample_ratio)),
            )
            if cfg.otlp_endpoint:
                exporter = OTLPSpanExporter(
                    endpoint=cfg.otlp_endpoint,
                    timeout=cfg.export_timeout_seconds,
                )
                provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            _configured = True
        app_id = id(app)
        if app_id not in _instrumented_apps:
            FastAPIInstrumentor.instrument_app(app, tracer_provider=trace.get_tracer_provider())
            _instrumented_apps.add(app_id)
    except Exception as exc:
        structlog.get_logger().warning(
            "observability_tracing_init_failed",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )


@contextmanager
def start_span(name: str, **attrs: Any) -> Iterator[Any]:
    tracer = trace.get_tracer("tagmemorag")
    with tracer.start_as_current_span(name) as span:
        safe_attrs = _sanitize_attrs(attrs)
        if safe_attrs:
            span.set_attributes(safe_attrs)
        yield span


def set_span_attributes(**attrs: Any) -> None:
    span = trace.get_current_span()
    safe_attrs = _sanitize_attrs(attrs)
    if safe_attrs:
        span.set_attributes(safe_attrs)


def reset_tracing_for_tests() -> None:
    global _configured
    _configured = False
    _instrumented_apps.clear()


def _sanitize_attrs(attrs: dict[str, Any]) -> dict[str, str | bool | int | float]:
    safe: dict[str, str | bool | int | float] = {}
    for key, value in attrs.items():
        if value is None:
            continue
        if not key.startswith("tagmemorag."):
            continue
        if isinstance(value, bool | int | float | str):
            safe[key] = value
        else:
            safe[key] = str(value)
    return safe
