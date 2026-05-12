from __future__ import annotations

from prometheus_client import generate_latest

from tagmemorag.observability import metrics


def test_metric_helpers_register_custom_series():
    collector = metrics.reset_metrics_for_tests()

    collector.record_search(
        kb_name="default",
        cache_status="miss",
        outcome="success",
        duration=0.01,
        result_count=2,
    )
    collector.record_cache_operation(operation="get", outcome="miss")
    collector.record_http_error(route="/search", status_code=429, error_code="RATE_LIMITED")
    collector.record_rate_limit(outcome="allowed")
    collector.record_rebuild_started(kb_name="default")
    collector.set_kbs_loaded(1)
    collector.set_embedder_ready(True)
    collector.record_startup_duration(0.25)

    body = generate_latest(metrics.get_registry()).decode("utf-8")

    assert "tagmemorag_search_requests_total" in body
    assert 'kb_name="default"' in body
    assert 'cache_status="miss"' in body
    assert "tagmemorag_cache_operations_total" in body
    assert 'tagmemorag_http_errors_total{error_code="RATE_LIMITED",route="/search",status_code="429"}' in body
    assert "tagmemorag_rate_limit_checks_total" in body
    assert "tagmemorag_rebuilds_total" in body
    assert "tagmemorag_kbs_loaded" in body
    assert "tagmemorag_embedder_ready" in body
    assert "tagmemorag_startup_duration_seconds 0.25" in body


def test_metric_label_contract_blocks_sensitive_dimensions():
    metrics.assert_label_contract()
    assert not (metrics.ALLOWED_LABEL_NAMES & metrics.FORBIDDEN_LABEL_NAMES)


def test_noop_metrics_when_disabled():
    collector = metrics.reset_metrics_for_tests(enabled=False)

    collector.record_search(kb_name="default", cache_status="miss", outcome="success", duration=0.01)

    assert collector.enabled is False
