from __future__ import annotations

from tagmemorag.replay.metrics import compute_deltas, compute_run_metrics, summarize_rerank
from tagmemorag.replay.models import ReplayCaseResult, ReplayPlan, ReplayRunMetrics


def _plan(plan_id: str, evidence=(), rerank=None) -> ReplayPlan:
    return ReplayPlan(
        plan_id=plan_id,
        kb_name="kb",
        query="q",
        created_at="2026-05-19T10:00:00Z",
        intent="text_answer",
        filters={},
        budget={},
        stored_evidence_ids=tuple(evidence),
        rerank=rerank,
    )


def test_compute_run_metrics_empty():
    assert compute_run_metrics([]) == ReplayRunMetrics()


def test_compute_run_metrics_target_only():
    plans = {
        "p1": _plan("p1", evidence=("ev_001", "ev_002")),
        "p2": _plan("p2"),
    }
    results = [
        ReplayCaseResult("p1", 1, True, result_count=2, top_chunk_id="c1", top_evidence_id="ev_001", evidence_ids=("ev_001", "ev_003"), latency_ms=10),
        ReplayCaseResult("p2", 1, True, result_count=0, latency_ms=20),
        ReplayCaseResult("p3", 1, False, error="boom", latency_ms=99),
    ]

    metrics = compute_run_metrics(results, plans_by_id=plans)

    assert metrics.queries_replayed == 2
    assert metrics.any_hit_rate == 0.5
    assert metrics.evidence_overlap_cases == 1
    assert metrics.evidence_overlap_at_k == 1 / 3
    assert metrics.top1_stability == 1.0
    assert metrics.latency_ms_p50 == 15


def test_compute_run_metrics_baseline_top1_stability():
    target = [
        ReplayCaseResult("p1", 2, True, result_count=1, top_chunk_id="c1"),
        ReplayCaseResult("p2", 2, True, result_count=1, top_chunk_id="c2"),
    ]
    baseline = {
        "p1": ReplayCaseResult("p1", 1, True, result_count=1, top_chunk_id="c1"),
        "p2": ReplayCaseResult("p2", 1, True, result_count=1, top_chunk_id="other"),
    }

    metrics = compute_run_metrics(target, baseline_by_id=baseline)

    assert metrics.top1_stability_cases == 2
    assert metrics.top1_stability == 0.5


def test_compute_deltas():
    target = ReplayRunMetrics(queries_replayed=2, any_hit_rate=1.0, latency_ms_p50=20)
    baseline = ReplayRunMetrics(queries_replayed=2, any_hit_rate=0.5, latency_ms_p50=10)

    deltas = compute_deltas(target, baseline)

    assert deltas["any_hit_rate_delta"] == 0.5
    assert deltas["latency_ms_p50_delta"] == 10


def test_summarize_rerank():
    plans = [
        _plan("p1", rerank={"vendor_used": "noop", "cache_status": "miss", "warnings": ["reranker_fallback:http_500"], "latency_ms": 12, "truncated_count": 2}),
        _plan("p2", rerank={"vendor_used": "siliconflow", "cache_status": "hit", "warnings": [], "latency_ms": 8, "truncated_count": 0}),
        _plan("p3"),
    ]

    summary = summarize_rerank(plans)

    assert summary["plans_with_rerank"] == 2
    assert summary["vendor_counts"] == {"noop": 1, "siliconflow": 1}
    assert summary["fallback_count"] == 1
    assert summary["fallback_rate"] == 0.5
    assert summary["cache_hit_rate"] == 0.5
    assert summary["warning_counts"] == {"reranker_fallback:http_500": 1}
    assert summary["truncated_total"] == 2
