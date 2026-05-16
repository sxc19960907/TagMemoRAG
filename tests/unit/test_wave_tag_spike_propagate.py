from __future__ import annotations

import pytest

from tagmemorag.tag_cooccurrence import CooccurrenceMatrix
from tagmemorag.wave_tag_spike import (
    SPIKE_BASE_DECAY,
    SPIKE_BASE_MOMENTUM,
    SPIKE_FIRING_THRESHOLD,
    SPIKE_MAX_EMERGENT_NODES,
    SPIKE_MAX_HOPS,
    SPIKE_MAX_NEIGHBORS_PER_NODE,
    SPIKE_TENSION_THRESHOLD,
    SPIKE_WORMHOLE_DECAY,
    propagate,
)


def _matrix(edges: dict[int, dict[int, float]]) -> CooccurrenceMatrix:
    edge_count = sum(len(v) for v in edges.values())
    return CooccurrenceMatrix(kb_name="test", edges=edges, built_at="2026-05-15", edge_count=edge_count)


def test_3node_chain_analytic_expectation():
    """AC3 anchor: A→B (0.5), B→C (0.4), seed A=1.0; analytic expectation:

    Hop 0: A fires (energy 1.0, momentum 2.0). A→B: tension=0.5<1.0 ⇒ base_decay=0.25,
           momentum_cost=1; injected = 1.0 * 0.5 * 0.25 = 0.125, nextMomentum=1.0.
    Hop 1: B fires (energy 0.125 ≥ 0.10, momentum 1.0). B→C: injected = 0.125 * 0.4 * 0.25 = 0.0125
           but 0.0125 < 0.01 is FALSE so it passes the gate. nextMomentum=0.0.
    Hop 2: C energy 0.0125 < 0.10 firing_threshold ⇒ no firing. propagated=False ⇒ break.

    Final accumulated: A=1.0, B=0.125, C=0.0125. 2 productive hops.
    """
    matrix = _matrix({1: {2: 0.5}, 2: {3: 0.4}})
    result = propagate({1: 1.0}, matrix)

    assert result.accumulated_energy[1] == pytest.approx(1.0)
    assert result.accumulated_energy[2] == pytest.approx(0.125)
    assert result.accumulated_energy[3] == pytest.approx(0.0125)
    assert result.seed_count == 1
    assert result.emergent_count == 2
    assert result.hops_executed == 2
    assert result.seed_ids == frozenset({1})


def test_wormhole_gate_triggers_at_high_tension():
    """AC8 anchor: edge with cooc_weight=1.5 (≥ tension_threshold=1.0) is a wormhole.

    Wormhole branch: decay=0.70 (vs 0.25), momentum_cost=0.
    Seed A=1.0, A→B=1.5 ⇒ injected = 1.0 * 1.5 * 0.70 = 1.05 (vs 0.375 base).
    """
    matrix = _matrix({1: {2: 1.5}})
    result = propagate({1: 1.0}, matrix)

    assert result.accumulated_energy[2] == pytest.approx(1.05)
    # Seed energy preserved
    assert result.accumulated_energy[1] == pytest.approx(1.0)


def test_wormhole_branch_disabled_below_threshold():
    """Edge weight just below tension_threshold uses base_decay."""
    matrix = _matrix({1: {2: 0.999}})
    result = propagate({1: 1.0}, matrix)

    assert result.accumulated_energy[2] == pytest.approx(1.0 * 0.999 * SPIKE_BASE_DECAY)


def test_wormhole_zero_momentum_cost_lets_chain_continue():
    """Wormhole edge costs no momentum; spike continues past depleted-momentum gate."""
    # Build a chain with all wormhole edges
    matrix = _matrix({1: {2: 1.5}, 2: {3: 1.5}, 3: {4: 1.5}})
    result = propagate({1: 1.0}, matrix, base_momentum=0.0)  # zero starting momentum
    # Without wormhole, base_momentum=0 ⇒ next_momentum=-1 < 0 ⇒ skip. With wormhole, momentum_cost=0
    # ⇒ next_momentum stays 0, propagation continues until energy/firing_threshold cuts it.
    # Seed energy 1.0 → B = 1.05 → C = 1.05 * 1.5 * 0.70 ≈ 1.1025 → D = 1.1025 * 1.5 * 0.70 ≈ 1.157625
    assert result.accumulated_energy[2] == pytest.approx(1.05)
    assert result.accumulated_energy[3] == pytest.approx(1.05 * 1.5 * SPIKE_WORMHOLE_DECAY)
    assert result.accumulated_energy[4] == pytest.approx(1.05 * 1.5 * SPIKE_WORMHOLE_DECAY * 1.5 * SPIKE_WORMHOLE_DECAY)


def test_residual_can_demote_wormhole_to_base():
    """tension = cooc * residual. Low residual keeps an otherwise-wormhole edge at base_decay."""
    matrix = _matrix({1: {2: 1.5}})  # would be wormhole with residual=1.0
    result = propagate({1: 1.0}, matrix, residuals={2: 0.5})  # tension = 1.5 * 0.5 = 0.75 < 1.0
    assert result.accumulated_energy[2] == pytest.approx(1.0 * 1.5 * SPIKE_BASE_DECAY)


def test_residual_can_promote_to_wormhole():
    """High residual upgrades a borderline edge to wormhole."""
    matrix = _matrix({1: {2: 0.7}})
    result = propagate({1: 1.0}, matrix, residuals={2: 2.0})  # tension = 1.4 ≥ 1.0
    assert result.accumulated_energy[2] == pytest.approx(1.0 * 0.7 * SPIKE_WORMHOLE_DECAY)


def test_missing_residual_count_tracks_fallback_lookups():
    result = propagate({1: 1.0}, _matrix({1: {2: 1.2, 3: 0.8}}), residuals={2: 0.5})

    assert result.missing_residual_count == 1


def test_firing_threshold_blocks_low_energy_seed():
    """A seed below firing_threshold does not propagate (stays as accumulated only)."""
    matrix = _matrix({1: {2: 0.5}})
    result = propagate({1: 0.05}, matrix)  # below 0.10 firing_threshold
    assert result.accumulated_energy == {1: pytest.approx(0.05)}
    assert result.hops_executed == 0


def test_injected_current_min_skips_tiny_pulse():
    """When injected current would be < 0.01, the neighbor is skipped."""
    # energy * cooc * 0.25 < 0.01 ⇒ 1.0 * 0.03 * 0.25 = 0.0075 < 0.01
    matrix = _matrix({1: {2: 0.03}})
    result = propagate({1: 1.0}, matrix)
    assert 2 not in result.accumulated_energy
    assert result.emergent_count == 0


def test_neighbor_cap_truncates_to_top_k():
    """Per-node neighbor cap keeps the top-K by weight; lower-weight edges dropped."""
    # 3 neighbors, cap=2 → only the two highest-weight edges fire
    matrix = _matrix({1: {2: 0.5, 3: 0.3, 4: 0.9}})
    result = propagate({1: 1.0}, matrix, max_neighbors=2)
    assert 4 in result.accumulated_energy  # weight 0.9 — kept
    assert 2 in result.accumulated_energy  # weight 0.5 — kept
    assert 3 not in result.accumulated_energy  # weight 0.3 — dropped
    assert result.truncated_by_cap is True


def test_neighbor_cap_default_does_not_set_flag_below_threshold():
    """With default cap=20 and only 3 edges, no cap hit."""
    matrix = _matrix({1: {2: 0.5, 3: 0.3, 4: 0.9}})
    result = propagate({1: 1.0}, matrix)
    assert result.truncated_by_cap is False


def test_emergent_cap_flag_when_exceeded():
    """When emergent_count exceeds max_emergent, truncated_by_cap is set."""
    # Synthesize a star graph with 5 emergents, cap to 3
    matrix = _matrix({1: {i: 0.9 for i in range(2, 7)}})
    result = propagate({1: 1.0}, matrix, max_emergent=3)
    assert result.emergent_count == 5
    assert result.truncated_by_cap is True


def test_max_hops_cap_breaks_iteration():
    """A long wormhole chain stops at max_hops even if energy > firing_threshold."""
    # 6 wormhole edges in a chain
    edges = {i: {i + 1: 1.5} for i in range(1, 7)}
    matrix = _matrix(edges)
    result = propagate({1: 1.0}, matrix, max_hops=2)
    assert result.hops_executed == 2
    assert result.truncated_by_cap is True
    # After 2 productive hops we should have reached node 3 (seed=1, hop1=2, hop2=3)
    assert 3 in result.accumulated_energy
    assert 4 not in result.accumulated_energy


def test_empty_seeds_returns_empty_result():
    """Propagation with no seeds is a no-op."""
    matrix = _matrix({1: {2: 0.5}})
    result = propagate({}, matrix)
    assert result.accumulated_energy == {}
    assert result.seed_count == 0
    assert result.emergent_count == 0
    assert result.hops_executed == 0


def test_empty_matrix_returns_seeds_only():
    """Empty matrix passes seeds through as accumulated, no propagation."""
    matrix = _matrix({})
    result = propagate({1: 0.7, 2: 0.3}, matrix)
    assert result.accumulated_energy == {1: pytest.approx(0.7), 2: pytest.approx(0.3)}
    assert result.seed_count == 2
    assert result.emergent_count == 0


def test_zero_or_negative_seed_weights_dropped():
    """Seeds with zero/negative weight are excluded (defensive)."""
    matrix = _matrix({1: {2: 0.5}})
    result = propagate({1: 1.0, 99: 0.0, 100: -0.5}, matrix)
    assert result.seed_ids == frozenset({1})
    assert 99 not in result.accumulated_energy
    assert 100 not in result.accumulated_energy


def test_aggregation_sums_pulses_at_shared_target():
    """Two seeds firing into the same neighbor accumulate energy additively."""
    # A→C (0.5), B→C (0.4); seeds A=1.0, B=1.0
    matrix = _matrix({1: {3: 0.5}, 2: {3: 0.4}})
    result = propagate({1: 1.0, 2: 1.0}, matrix)
    # Both contribute to C: 1.0*0.5*0.25 + 1.0*0.4*0.25 = 0.125 + 0.10 = 0.225
    assert result.accumulated_energy[3] == pytest.approx(0.125 + 0.10)


def test_seed_kept_when_also_a_target():
    """Seed energy is preserved even if propagation later targets the seed."""
    # 1→2 (0.5), 2→1 (0.5); seed 1=1.0
    matrix = _matrix({1: {2: 0.5}, 2: {1: 0.5}})
    result = propagate({1: 1.0}, matrix)
    # After hop 0: A=1.0 (seed), B = 1.0 * 0.5 * 0.25 = 0.125
    # Hop 1: B fires (0.125 ≥ 0.10), B→A injected = 0.125 * 0.5 * 0.25 = 0.015625 (≥0.01)
    # A accumulates: 1.0 + 0.015625 = 1.015625
    assert result.accumulated_energy[1] == pytest.approx(1.015625)
    assert 1 in result.seed_ids
    # Emergent excludes seeds — only B is emergent
    assert result.emergent_count == 1
