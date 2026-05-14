"""Unit tests for baseline loading and -2% threshold derivation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tagmemorag.eval.dataset import EvalSuiteError, EvalThresholds
from tagmemorag.eval.runner import (
    BASELINE_FLOOR_DELTA,
    baseline_thresholds_for,
    load_baseline,
)


def _write_baseline(tmp_path: Path, payload: dict) -> Path:
    target = tmp_path / "baseline.json"
    target.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return target


def test_load_baseline_returns_suite_metric_map(tmp_path: Path):
    baseline = _write_baseline(
        tmp_path,
        {
            "embedder": "hashing",
            "captured_at": "2026-05-14T00:00:00Z",
            "thresholds_applied": {"floor_delta": 0.02},
            "suites": {
                "fault_codes.jsonl": {
                    "precision_at_k": 0.6,
                    "recall_at_k": 1.0,
                    "mrr": 0.9,
                    "hit_at_k": 1.0,
                }
            },
        },
    )

    suites = load_baseline(baseline)

    assert suites == {
        "fault_codes.jsonl": {"precision_at_k": 0.6, "recall_at_k": 1.0, "mrr": 0.9, "hit_at_k": 1.0}
    }


def test_load_baseline_missing_file_raises(tmp_path: Path):
    with pytest.raises(EvalSuiteError, match="baseline file not found"):
        load_baseline(tmp_path / "missing.json")


def test_load_baseline_rejects_invalid_json(tmp_path: Path):
    target = tmp_path / "broken.json"
    target.write_text("{not json", encoding="utf-8")

    with pytest.raises(EvalSuiteError, match="not valid JSON"):
        load_baseline(target)


def test_load_baseline_requires_suites_object(tmp_path: Path):
    target = _write_baseline(tmp_path, {"embedder": "hashing"})

    with pytest.raises(EvalSuiteError, match="missing the 'suites' object"):
        load_baseline(target)


def test_baseline_thresholds_for_subtracts_floor_delta():
    metrics = {"precision_at_k": 0.6, "recall_at_k": 0.9, "mrr": 0.9, "hit_at_k": 1.0}

    thresholds = baseline_thresholds_for(metrics, case_thresholds=EvalThresholds())

    assert thresholds.min_precision_at_k == pytest.approx(0.6 - BASELINE_FLOOR_DELTA)
    assert thresholds.min_recall_at_k == pytest.approx(0.9 - BASELINE_FLOOR_DELTA)
    assert thresholds.min_mrr == pytest.approx(0.9 - BASELINE_FLOOR_DELTA)
    assert thresholds.min_hit_at_k == pytest.approx(1.0 - BASELINE_FLOOR_DELTA)


def test_baseline_thresholds_for_clamps_to_case_floor():
    metrics = {"precision_at_k": 0.05, "recall_at_k": 0.5, "mrr": 0.6, "hit_at_k": 0.5}
    case_thresholds = EvalThresholds(min_recall_at_k=0.4, min_mrr=0.7, min_hit_at_k=0.3)

    thresholds = baseline_thresholds_for(metrics, case_thresholds=case_thresholds)

    assert thresholds.min_recall_at_k == pytest.approx(0.5 - BASELINE_FLOOR_DELTA)
    assert thresholds.min_mrr == pytest.approx(0.7)
    assert thresholds.min_hit_at_k == pytest.approx(0.5 - BASELINE_FLOOR_DELTA)


def test_baseline_thresholds_for_clamps_to_zero_one_range():
    metrics = {"precision_at_k": 0.0, "recall_at_k": 1.5, "mrr": -0.1, "hit_at_k": 0.005}

    thresholds = baseline_thresholds_for(metrics, case_thresholds=EvalThresholds())

    assert thresholds.min_precision_at_k == pytest.approx(0.0)
    assert thresholds.min_recall_at_k == pytest.approx(1.0)
    assert thresholds.min_mrr == pytest.approx(0.0)
    assert thresholds.min_hit_at_k == pytest.approx(0.0)


def test_baseline_thresholds_for_passes_through_when_metric_absent():
    case = EvalThresholds(min_recall_at_k=0.3)

    thresholds = baseline_thresholds_for({}, case_thresholds=case)

    assert thresholds.min_recall_at_k == 0.3
    assert thresholds.min_mrr is None
