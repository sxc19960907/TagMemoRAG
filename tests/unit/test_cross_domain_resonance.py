"""Phase 3 — `detect_cross_domain_resonance` helper unit tests.

Locks the V6 EPAModule.js:170-201 port (commit aff66193). The helper itself is
pure (no IO / config dependencies) so each case constructs synthetic
``dominant_axes`` directly.
"""

from __future__ import annotations

import math

import pytest

from tagmemorag.wave_tag_spike import (
    _RESONANCE_CO_ACTIVATION_THRESHOLD,
    detect_cross_domain_resonance,
)


def _axis(label: str, energy: float) -> dict:
    return {"label": label, "energy": float(energy), "index": 0, "projection": 0.0}


def test_resonance_dominant_axes_empty_returns_zero():
    resonance, bridges = detect_cross_domain_resonance([])
    assert resonance == 0.0
    assert bridges == []


def test_resonance_dominant_axes_single_returns_zero():
    resonance, bridges = detect_cross_domain_resonance([_axis("Tech", 0.9)])
    assert resonance == 0.0
    assert bridges == []


def test_resonance_below_threshold_excluded():
    # co_activation = sqrt(0.5 * 0.04) = sqrt(0.02) ≈ 0.1414 < 0.15
    axes = [_axis("Tech", 0.5), _axis("Tail", 0.04)]
    resonance, bridges = detect_cross_domain_resonance(axes)
    assert bridges == []
    assert resonance == 0.0


def test_resonance_single_bridge_balanced():
    # co_activation = sqrt(0.5 * 0.5) = 0.5 > 0.15
    axes = [_axis("Tech", 0.5), _axis("Logic", 0.5)]
    resonance, bridges = detect_cross_domain_resonance(axes)
    assert len(bridges) == 1
    bridge = bridges[0]
    assert bridge["from"] == "Tech"
    assert bridge["to"] == "Logic"
    assert math.isclose(bridge["strength"], 0.5, rel_tol=1e-9)
    assert math.isclose(bridge["balance"], 1.0, rel_tol=1e-9)
    assert math.isclose(resonance, 0.5, rel_tol=1e-9)


def test_resonance_multiple_bridges_sum_correctly():
    # axes: [0.5, 0.4, 0.3] ⇒ pairs vs top:
    #   (0,1) co = sqrt(0.5*0.4) = sqrt(0.20) ≈ 0.4472
    #   (0,2) co = sqrt(0.5*0.3) = sqrt(0.15) ≈ 0.3873
    # Both > 0.15 ⇒ resonance ≈ 0.8345
    axes = [_axis("A", 0.5), _axis("B", 0.4), _axis("C", 0.3)]
    resonance, bridges = detect_cross_domain_resonance(axes)
    assert len(bridges) == 2
    expected = math.sqrt(0.20) + math.sqrt(0.15)
    assert math.isclose(resonance, expected, rel_tol=1e-9)
    # Bridges always pivot on the top axis ("A"); secondary order = input order.
    assert [b["to"] for b in bridges] == ["B", "C"]
    assert all(b["from"] == "A" for b in bridges)


def test_resonance_balance_extremes():
    # top.energy=0.9, sec.energy=0.1 ⇒ co_act = sqrt(0.09) = 0.3 > 0.15
    # balance = 0.1 / 0.9 ≈ 0.1111
    axes = [_axis("Loud", 0.9), _axis("Quiet", 0.1)]
    resonance, bridges = detect_cross_domain_resonance(axes)
    assert len(bridges) == 1
    assert math.isclose(bridges[0]["strength"], 0.3, rel_tol=1e-9)
    assert math.isclose(bridges[0]["balance"], 0.1 / 0.9, rel_tol=1e-9)
    assert math.isclose(resonance, 0.3, rel_tol=1e-9)


def test_resonance_handles_missing_energy_field():
    # `energy` missing on either side ⇒ defaulted to 0.0, never raises.
    axes = [{"label": "A"}, {"label": "B"}]
    resonance, bridges = detect_cross_domain_resonance(axes)
    assert resonance == 0.0
    assert bridges == []


def test_resonance_threshold_is_strict_inequality():
    # Construct axes whose product equals the threshold² so co_act == 0.15
    # exactly; the source uses `>`, not `>=`, so this must be excluded.
    target = _RESONANCE_CO_ACTIVATION_THRESHOLD ** 2  # 0.0225
    axes = [_axis("A", target), _axis("B", 1.0)]
    resonance, bridges = detect_cross_domain_resonance(axes)
    assert math.isclose(
        math.sqrt(target * 1.0), _RESONANCE_CO_ACTIVATION_THRESHOLD, rel_tol=1e-12
    )
    assert bridges == []
    assert resonance == 0.0


def test_resonance_handles_dataclass_like_axes():
    """Accept axes exposing fields via getattr (forward-compat)."""

    class _Axis:
        def __init__(self, label: str, energy: float) -> None:
            self.label = label
            self.energy = energy
            self.index = 0
            self.projection = 0.0

    axes = [_Axis("Tech", 0.5), _Axis("Logic", 0.5)]
    resonance, bridges = detect_cross_domain_resonance(axes)
    assert math.isclose(resonance, 0.5, rel_tol=1e-9)
    assert bridges and bridges[0]["from"] == "Tech"


def test_resonance_negative_energy_clamped_to_zero():
    # Defensive: energy values outside the [0,1] EPA contract should not crash
    # nor flip the sqrt sign. `max(0.0, ...)` clamp is in the helper.
    axes = [_axis("A", -0.5), _axis("B", 0.5)]
    resonance, bridges = detect_cross_domain_resonance(axes)
    assert resonance == 0.0
    assert bridges == []


@pytest.mark.parametrize("k", [2, 3, 5, 8])
def test_resonance_log_domain_amplification_consistent(k: int):
    """Sanity: log(1 + resonance) increases monotonically with axis count
    when each secondary axis stays at the same fixed energy as the top."""
    axes = [_axis(f"A{i}", 0.5) for i in range(k)]
    resonance, bridges = detect_cross_domain_resonance(axes)
    # k-1 bridges, each strength = sqrt(0.5*0.5) = 0.5
    expected = 0.5 * (k - 1)
    assert math.isclose(resonance, expected, rel_tol=1e-9)
    assert len(bridges) == k - 1
    assert math.log(1.0 + resonance) > math.log(1.0 + 0.0)
