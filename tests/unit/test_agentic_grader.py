from __future__ import annotations

from tagmemorag.agentic.grader import CragGradeThresholds, grade_rerank_result
from tagmemorag.reranker.base import RerankResult, RerankResultItem


def _result(items, *, vendor_used="qwen", cache_status="miss") -> RerankResult:
    return RerankResult(
        items=tuple(RerankResultItem(chunk_id=f"c{idx}", raw_score=score, calibrated_score=score) for idx, score in enumerate(items)),
        truncated_chunk_ids=(),
        vendor_used=vendor_used,
        cache_status=cache_status,
        latency_ms=3,
    )


def test_grade_high_when_top_score_and_margin_pass():
    grade = grade_rerank_result(_result([0.82, 0.55]))

    assert grade.signal == "high"
    assert grade.reason == "high_confidence"
    assert grade.top1_score == 0.82
    assert round(grade.margin, 2) == 0.27
    assert grade.depth == 2


def test_grade_inconclusive_when_top_score_high_but_margin_low():
    grade = grade_rerank_result(_result([0.82, 0.80]))

    assert grade.signal == "inconclusive"
    assert grade.reason == "inconclusive_margin"


def test_grade_low_when_top_score_below_threshold():
    grade = grade_rerank_result(_result([0.1, 0.05]))

    assert grade.signal == "low"
    assert grade.reason == "low_score"


def test_grade_low_when_no_items():
    grade = grade_rerank_result(_result([]))

    assert grade.signal == "low"
    assert grade.reason == "empty_rerank_items"


def test_grade_no_signal_for_noop_or_skipped():
    assert grade_rerank_result(_result([0.9], vendor_used="noop")).signal == "no_signal"
    assert grade_rerank_result(_result([0.9], cache_status="skipped")).signal == "no_signal"


def test_grade_honors_custom_thresholds():
    grade = grade_rerank_result(
        _result([0.45, 0.1]),
        CragGradeThresholds(high_score=0.4, low_score=0.1, min_margin=0.2),
    )

    assert grade.signal == "high"
