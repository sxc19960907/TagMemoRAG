from __future__ import annotations

from collections import Counter
from typing import Any

from .models import ReplayCaseResult, ReplayPlan, ReplayRunMetrics


def compute_run_metrics(
    results: list[ReplayCaseResult],
    plans_by_id: dict[str, ReplayPlan] | None = None,
    baseline_by_id: dict[str, ReplayCaseResult] | None = None,
) -> ReplayRunMetrics:
    successful = [item for item in results if item.query_replayed]
    if not successful:
        return ReplayRunMetrics()

    any_hit_rate = sum(1 for item in successful if item.result_count > 0) / len(successful)
    overlap_values: list[float] = []
    top1_matches = 0
    top1_cases = 0
    for item in successful:
        plan = plans_by_id.get(item.plan_id) if plans_by_id else None
        if plan is not None and plan.stored_evidence_ids:
            overlap_values.append(_jaccard(set(plan.stored_evidence_ids), set(item.evidence_ids)))
        baseline = baseline_by_id.get(item.plan_id) if baseline_by_id else None
        if baseline is not None and baseline.query_replayed and baseline.top_chunk_id and item.top_chunk_id:
            top1_cases += 1
            top1_matches += 1 if baseline.top_chunk_id == item.top_chunk_id else 0
        elif plan is not None and plan.stored_evidence_ids and item.top_evidence_id:
            top1_cases += 1
            top1_matches += 1 if plan.stored_evidence_ids[0] == item.top_evidence_id else 0

    latencies = [float(item.latency_ms) for item in successful]
    return ReplayRunMetrics(
        queries_replayed=len(successful),
        any_hit_rate=any_hit_rate,
        evidence_overlap_at_k=(sum(overlap_values) / len(overlap_values)) if overlap_values else 0.0,
        evidence_overlap_cases=len(overlap_values),
        top1_stability=(top1_matches / top1_cases) if top1_cases else 0.0,
        top1_stability_cases=top1_cases,
        latency_ms_p50=_percentile(latencies, 50),
        latency_ms_p95=_percentile(latencies, 95),
    )


def compute_deltas(target: ReplayRunMetrics, baseline: ReplayRunMetrics) -> dict[str, float]:
    target_dict = target.to_dict()
    baseline_dict = baseline.to_dict()
    out: dict[str, float] = {}
    for key, target_value in target_dict.items():
        baseline_value = baseline_dict.get(key)
        if isinstance(target_value, (int, float)) and isinstance(baseline_value, (int, float)):
            out[f"{key}_delta"] = round(float(target_value) - float(baseline_value), 6)
    return out


def summarize_rerank(plans: list[ReplayPlan]) -> dict[str, Any]:
    reranked = [plan for plan in plans if plan.rerank]
    vendor_counts: Counter[str] = Counter()
    cache_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    latencies: list[float] = []
    fallback_count = 0
    truncated_total = 0
    for plan in reranked:
        rerank = dict(plan.rerank or {})
        vendor = str(rerank.get("vendor_used") or "")
        cache_status = str(rerank.get("cache_status") or "")
        warnings = [str(item) for item in rerank.get("warnings") or []]
        vendor_counts[vendor or "unknown"] += 1
        cache_counts[cache_status or "unknown"] += 1
        for warning in warnings:
            warning_counts[warning] += 1
        if vendor == "noop" or any(warning.startswith("reranker_fallback") for warning in warnings):
            fallback_count += 1
        try:
            latencies.append(float(rerank.get("latency_ms") or 0.0))
        except (TypeError, ValueError):
            pass
        try:
            truncated_total += int(rerank.get("truncated_count") or 0)
        except (TypeError, ValueError):
            pass
    return {
        "plans_with_rerank": len(reranked),
        "vendor_counts": dict(sorted(vendor_counts.items())),
        "fallback_count": fallback_count,
        "fallback_rate": round((fallback_count / len(reranked)) if reranked else 0.0, 6),
        "cache_counts": dict(sorted(cache_counts.items())),
        "cache_hit_rate": round((cache_counts.get("hit", 0) / len(reranked)) if reranked else 0.0, 6),
        "warning_counts": dict(sorted(warning_counts.items())),
        "latency_ms_p50": round(_percentile(latencies, 50), 3),
        "latency_ms_p95": round(_percentile(latencies, 95), 3),
        "truncated_total": truncated_total,
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    left.discard("")
    right.discard("")
    if not left and not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (percentile / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


__all__ = ["compute_deltas", "compute_run_metrics", "summarize_rerank"]
