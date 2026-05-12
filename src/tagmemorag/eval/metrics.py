from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RankingMetrics:
    precision_at_k: float
    recall_at_k: float
    mrr: float
    hit_at_k: float

    def to_dict(self) -> dict[str, float]:
        return {
            "precision_at_k": _round(self.precision_at_k),
            "recall_at_k": _round(self.recall_at_k),
            "mrr": _round(self.mrr),
            "hit_at_k": _round(self.hit_at_k),
        }


def compute_ranking_metrics(rank_to_expected_indexes: list[set[int]], expected_count: int, k: int) -> RankingMetrics:
    if expected_count <= 0:
        raise ValueError("expected_count must be positive")
    if k <= 0:
        raise ValueError("k must be positive")
    top = rank_to_expected_indexes[:k]
    matched: set[int] = set()
    relevant_result_count = 0
    first_relevant_rank: int | None = None
    for rank, expected_indexes in enumerate(top, 1):
        if expected_indexes:
            relevant_result_count += 1
            if first_relevant_rank is None:
                first_relevant_rank = rank
            matched.update(expected_indexes)
    return RankingMetrics(
        precision_at_k=relevant_result_count / k,
        recall_at_k=len(matched) / expected_count,
        mrr=0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank,
        hit_at_k=1.0 if first_relevant_rank is not None else 0.0,
    )


def aggregate_metrics(metrics: list[RankingMetrics]) -> RankingMetrics:
    if not metrics:
        return RankingMetrics(0.0, 0.0, 0.0, 0.0)
    count = len(metrics)
    return RankingMetrics(
        precision_at_k=sum(item.precision_at_k for item in metrics) / count,
        recall_at_k=sum(item.recall_at_k for item in metrics) / count,
        mrr=sum(item.mrr for item in metrics) / count,
        hit_at_k=sum(item.hit_at_k for item in metrics) / count,
    )


def _round(value: float) -> float:
    return round(float(value), 6)
