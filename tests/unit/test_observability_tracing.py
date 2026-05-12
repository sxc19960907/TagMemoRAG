from __future__ import annotations

from fastapi import FastAPI

from tagmemorag.config import ObservabilityConfig, Settings
from tagmemorag.observability.tracing import configure_tracing, reset_tracing_for_tests, set_span_attributes, start_span


def test_disabled_tracing_does_not_require_exporter():
    reset_tracing_for_tests()
    app = FastAPI()
    cfg = Settings(observability=ObservabilityConfig(tracing={"enabled": False}))

    configure_tracing(app, cfg)
    with start_span("tagmemorag.test", **{"tagmemorag.kb_name": "default"}):
        set_span_attributes(**{"tagmemorag.result_count": 1})


def test_tracing_setup_is_idempotent_without_endpoint():
    reset_tracing_for_tests()
    app = FastAPI()
    cfg = Settings(observability=ObservabilityConfig(tracing={"enabled": True, "sample_ratio": 0.25}))

    configure_tracing(app, cfg)
    configure_tracing(app, cfg)


def test_span_helpers_filter_non_tagmemorag_attrs():
    with start_span("tagmemorag.test", **{"tagmemorag.kb_name": "default", "question": "secret"}) as span:
        set_span_attributes(**{"tagmemorag.cache_status": "miss", "trace_id": "nope"})

    assert span is not None
