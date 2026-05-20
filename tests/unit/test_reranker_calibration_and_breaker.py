"""Tests for reranker calibration + circuit breaker (T3 Slice 2)."""

from __future__ import annotations

import math
import threading
import time

import pytest

from tagmemorag.reranker.calibration import (
    IdentityCalibrator,
    MinMaxCalibrator,
    SigmoidCalibrator,
    ZScoreCalibrator,
    build_calibrator,
)
from tagmemorag.reranker.circuit_breaker import CircuitBreaker


# ---------- calibration: shared edge cases ----------

@pytest.mark.parametrize("cls", [MinMaxCalibrator, ZScoreCalibrator, SigmoidCalibrator, IdentityCalibrator])
def test_calibrator_handles_empty(cls):
    c = cls()
    assert c.calibrate([]) == []


@pytest.mark.parametrize("cls", [MinMaxCalibrator, ZScoreCalibrator, SigmoidCalibrator])
def test_calibrator_single_element_is_midpoint(cls):
    c = cls()
    out = c.calibrate([5.7])
    assert out == [0.5]


def test_identity_single_element_passthrough():
    """Identity is the only calibrator that returns the original (no degeneracy fallback)."""
    c = IdentityCalibrator()
    assert c.calibrate([5.7]) == [5.7]


@pytest.mark.parametrize("cls", [MinMaxCalibrator, ZScoreCalibrator, SigmoidCalibrator])
def test_calibrator_all_equal_is_midpoint(cls):
    c = cls()
    assert c.calibrate([3.0, 3.0, 3.0]) == [0.5, 0.5, 0.5]


def test_identity_all_equal_passthrough():
    c = IdentityCalibrator()
    assert c.calibrate([3.0, 3.0, 3.0]) == [3.0, 3.0, 3.0]


# ---------- min-max specifics ----------

def test_minmax_normal_case():
    c = MinMaxCalibrator()
    out = c.calibrate([1.0, 2.0, 3.0, 4.0, 5.0])
    assert out == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_minmax_handles_negative_scores():
    c = MinMaxCalibrator()
    out = c.calibrate([-2.0, 0.0, 2.0])
    assert out == [0.0, 0.5, 1.0]


def test_minmax_preserves_relative_order():
    c = MinMaxCalibrator()
    raw = [3.0, 1.0, 5.0, 2.0]
    out = c.calibrate(raw)
    # rank order matches raw
    rank_raw = sorted(range(4), key=lambda i: raw[i])
    rank_out = sorted(range(4), key=lambda i: out[i])
    assert rank_raw == rank_out


# ---------- z-score specifics ----------

def test_zscore_mean_zero_std_one():
    c = ZScoreCalibrator()
    out = c.calibrate([1.0, 2.0, 3.0, 4.0, 5.0])
    mean = sum(out) / len(out)
    assert mean == pytest.approx(0.0, abs=1e-9)
    var = sum((s - mean) ** 2 for s in out) / len(out)
    assert var == pytest.approx(1.0, abs=1e-9)


# ---------- sigmoid specifics ----------

def test_sigmoid_bounded_in_zero_one():
    c = SigmoidCalibrator()
    out = c.calibrate([-100.0, 0.0, 100.0])
    # ±100 saturates to 0 and 1 in float64; that's still bounded, just at boundary.
    assert all(0.0 <= x <= 1.0 for x in out)
    assert out[1] == pytest.approx(0.5, abs=1e-9)
    assert out[0] < out[1] < out[2]


def test_sigmoid_no_overflow_at_extreme_values():
    c = SigmoidCalibrator()
    out = c.calibrate([-1e6, 1e6])
    assert all(0.0 <= x <= 1.0 for x in out)


# ---------- identity specifics ----------

def test_identity_passthrough_normal():
    c = IdentityCalibrator()
    assert c.calibrate([0.5, 1.5, 2.5]) == [0.5, 1.5, 2.5]


# ---------- registry ----------

def test_build_calibrator_returns_correct_type():
    assert isinstance(build_calibrator("minmax"), MinMaxCalibrator)
    assert isinstance(build_calibrator("zscore"), ZScoreCalibrator)
    assert isinstance(build_calibrator("sigmoid"), SigmoidCalibrator)
    assert isinstance(build_calibrator("identity"), IdentityCalibrator)


def test_build_calibrator_unknown_raises():
    with pytest.raises(ValueError):
        build_calibrator("unknown")  # type: ignore[arg-type]


# ---------- CircuitBreaker ----------

def test_breaker_initially_closed():
    b = CircuitBreaker(threshold=3, cooldown_s=10)
    assert b.is_open() is False


def test_breaker_opens_after_threshold_failures():
    b = CircuitBreaker(threshold=3, cooldown_s=10)
    b.record_failure()
    assert b.is_open() is False
    b.record_failure()
    assert b.is_open() is False
    b.record_failure()
    assert b.is_open() is True


def test_breaker_success_resets_failures():
    b = CircuitBreaker(threshold=3, cooldown_s=10)
    b.record_failure()
    b.record_failure()
    b.record_success()
    b.record_failure()
    assert b.is_open() is False  # only 1 failure after reset
    b.record_failure()
    assert b.is_open() is False  # 2 failures
    b.record_failure()
    assert b.is_open() is True  # 3rd → open


def test_breaker_cooldown_resets_after_elapsed():
    b = CircuitBreaker(threshold=2, cooldown_s=0.1)
    b.record_failure()
    b.record_failure()
    assert b.is_open() is True
    time.sleep(0.15)
    # After cooldown, is_open() returns False AND clears state
    assert b.is_open() is False
    b.record_failure()
    assert b.is_open() is False  # only 1 failure since reset


def test_breaker_record_success_clears_open_state():
    """If something records a success while in cooldown, breaker reopens to closed."""
    b = CircuitBreaker(threshold=1, cooldown_s=10)
    b.record_failure()
    assert b.is_open() is True
    b.record_success()
    assert b.is_open() is False


def test_breaker_state_snapshot():
    b = CircuitBreaker(threshold=3, cooldown_s=30)
    s = b.state()
    assert s["threshold"] == 3
    assert s["cooldown_s"] == 30.0
    assert s["is_open"] is False
    assert s["failures"] == 0


def test_breaker_thread_safety_smoke():
    """Many threads recording failures — no race-induced corruption."""
    b = CircuitBreaker(threshold=100, cooldown_s=10)
    workers = [threading.Thread(target=lambda: [b.record_failure() for _ in range(10)]) for _ in range(10)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    s = b.state()
    assert s["failures"] == 100  # 10 threads × 10 failures


def test_breaker_invalid_threshold_raises():
    with pytest.raises(ValueError):
        CircuitBreaker(threshold=0)


def test_breaker_invalid_cooldown_raises():
    with pytest.raises(ValueError):
        CircuitBreaker(threshold=3, cooldown_s=-1)
