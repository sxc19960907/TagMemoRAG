from __future__ import annotations

import pytest

from tagmemorag.eval.metrics import aggregate_metrics, compute_ranking_metrics


def test_compute_ranking_metrics_hit_at_first_rank():
    metrics = compute_ranking_metrics([{0}, set(), {1}], expected_count=2, k=5)

    assert metrics.precision_at_k == 0.4
    assert metrics.recall_at_k == 1.0
    assert metrics.mrr == 1.0
    assert metrics.hit_at_k == 1.0


def test_compute_ranking_metrics_no_hit():
    metrics = compute_ranking_metrics([set(), set()], expected_count=1, k=2)

    assert metrics.precision_at_k == 0.0
    assert metrics.recall_at_k == 0.0
    assert metrics.mrr == 0.0
    assert metrics.hit_at_k == 0.0


def test_compute_ranking_metrics_deduplicates_expectation_matches_for_recall():
    metrics = compute_ranking_metrics([{0}, {0}], expected_count=1, k=2)

    assert metrics.precision_at_k == 1.0
    assert metrics.recall_at_k == 1.0


def test_aggregate_metrics_macro_average():
    first = compute_ranking_metrics([{0}], expected_count=1, k=1)
    second = compute_ranking_metrics([set()], expected_count=1, k=1)

    aggregate = aggregate_metrics([first, second])

    assert aggregate.precision_at_k == 0.5
    assert aggregate.recall_at_k == 0.5
    assert aggregate.mrr == 0.5
    assert aggregate.hit_at_k == 0.5


def test_compute_ranking_metrics_requires_positive_expected_count():
    with pytest.raises(ValueError, match="expected_count"):
        compute_ranking_metrics([], expected_count=0, k=1)
