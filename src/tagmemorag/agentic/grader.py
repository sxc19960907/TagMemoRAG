from __future__ import annotations

from dataclasses import dataclass

from ..reranker.base import RerankResult
from .state import GradeOutcome


@dataclass(frozen=True)
class CragGradeThresholds:
    high_score: float = 0.6
    low_score: float = 0.2
    min_margin: float = 0.05
    min_depth: int = 1


def grade_rerank_result(
    result: RerankResult,
    thresholds: CragGradeThresholds = CragGradeThresholds(),
) -> GradeOutcome:
    if result.cache_status == "skipped" or result.vendor_used == "noop":
        return GradeOutcome(signal="no_signal", reason="reranker_no_signal")
    if not result.items:
        return GradeOutcome(signal="low", reason="empty_rerank_items")

    items = tuple(sorted(result.items, key=lambda item: item.calibrated_score, reverse=True))
    top1 = float(items[0].calibrated_score)
    top2 = float(items[1].calibrated_score) if len(items) > 1 else 0.0
    margin = top1 - top2 if len(items) > 1 else top1
    depth = len(items)

    if top1 >= thresholds.high_score and margin >= thresholds.min_margin and depth >= thresholds.min_depth:
        return GradeOutcome(top1_score=top1, margin=margin, depth=depth, signal="high", reason="high_confidence")
    if top1 <= thresholds.low_score:
        return GradeOutcome(top1_score=top1, margin=margin, depth=depth, signal="low", reason="low_score")
    return GradeOutcome(top1_score=top1, margin=margin, depth=depth, signal="inconclusive", reason="inconclusive_margin")


__all__ = ["CragGradeThresholds", "grade_rerank_result"]
