"""Unit tests for ResidualPyramid (Phase 2b-1, L2 port depth)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from tagmemorag.residual_pyramid import (
    HandshakeFeatures,
    PyramidFeatures,
    ResidualPyramid,
    _analyze_handshakes,
    _extract_features,
    _gram_schmidt_project,
)


@dataclass
class _TagRow:
    tag_id: int
    name: str
    vector: np.ndarray


def _make_orthogonal_basis(dim: int, n: int) -> list[np.ndarray]:
    """Return n unit-norm orthogonal vectors of dimension dim."""
    eye = np.eye(dim, dtype=np.float32)
    return [eye[i] for i in range(n)]


def test_analyze_empty_query_returns_empty_result():
    dim = 8
    rows = [_TagRow(i, f"t{i}", np.eye(dim, dtype=np.float32)[i]) for i in range(4)]
    pyramid = ResidualPyramid(rows, dim=dim, max_levels=3, top_k=2)
    result = pyramid.analyze(np.zeros(dim, dtype=np.float32))
    assert result.levels == ()
    assert result.total_explained_energy == 0.0
    assert result.features.depth == 0
    assert result.features.tag_memo_activation == 0.0
    # Final residual = original (zero)
    assert np.allclose(result.final_residual, 0.0)


def test_analyze_two_level_decomposition_with_synthetic_orthogonal_tags():
    """Query = 0.6*e1 + 0.6*e2 + 0.6*e3 + 0.1*e4 (orthonormal basis).

    With top_k=2 per level, level-0 picks e1+e2 (similarity 0.6 each),
    level-1 picks e3 (then maybe e4). Total explained energy ≈ all of (0.36+0.36+0.36+0.01)/1.09 ~= 0.99.
    """
    dim = 6
    e = np.eye(dim, dtype=np.float32)
    rows = [_TagRow(i, f"t{i}", e[i]) for i in range(4)]
    query = (0.6 * e[0] + 0.6 * e[1] + 0.6 * e[2] + 0.1 * e[3]).astype(np.float32)

    pyramid = ResidualPyramid(rows, dim=dim, max_levels=3, top_k=2, min_energy_ratio=0.01)
    result = pyramid.analyze(query)

    assert result.features.depth >= 2
    # Should explain almost all energy
    assert result.total_explained_energy > 0.95
    assert result.features.coverage > 0.95
    # tag_memo_activation in [0, 1]
    assert 0.0 <= result.features.tag_memo_activation <= 1.0


def test_gram_schmidt_handles_linearly_dependent_tags():
    """Two identical tag vectors → second basis_coeff = 0."""
    dim = 4
    v = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    query = np.array([1.0, 0.5, 0.0, 0.0], dtype=np.float32)
    projection, residual, coeffs = _gram_schmidt_project(query, [v, v])
    # First tag absorbs query.x component
    assert coeffs[0] > 0.99
    # Second tag is linearly dependent → 0 contribution
    assert coeffs[1] == 0.0
    # Residual orthogonal to v
    assert abs(float(np.dot(residual, v))) < 1e-5


def test_analyze_early_stops_on_min_energy_ratio():
    """Crafted: level-0 explains > 90% so iteration stops at level 0 with min_energy_ratio=0.1."""
    dim = 4
    e = np.eye(dim, dtype=np.float32)
    rows = [_TagRow(i, f"t{i}", e[i]) for i in range(4)]
    # Query lies almost entirely in span of {e0}: 0.99*e0 + 0.01*e1
    query = (0.99 * e[0] + 0.01 * e[1]).astype(np.float32)

    pyramid = ResidualPyramid(rows, dim=dim, max_levels=3, top_k=1, min_energy_ratio=0.1)
    result = pyramid.analyze(query)

    # top_k=1 picks e0 first; e0 explains > 99% → residual ratio < 0.1 → break
    assert result.features.depth == 1


def test_extract_features_formula_locked():
    """Math anchor: coverage=0.6, coherence=0.5, noise=0.2 → tag_memo_activation = 0.24."""
    handshake = HandshakeFeatures(
        direction_coherence=0.7,   # not used in tag_memo_activation
        pattern_strength=0.5,      # → coherence
        novelty_signal=0.7,        # → directional_novelty contribution
        noise_signal=0.2,
    )
    # Build a fake levels[0] with handshake_features attached
    from tagmemorag.residual_pyramid import PyramidLevel

    level0 = PyramidLevel(
        level=0,
        tags=(),
        projection_magnitude=0.0,
        residual_magnitude=0.0,
        residual_energy_ratio=0.4,
        energy_explained=0.6,
        handshake_features=handshake,
    )
    features = _extract_features([level0], total_explained_energy=0.6)
    assert features.depth == 1
    assert pytest.approx(features.coverage, rel=1e-6) == 0.6
    assert pytest.approx(features.coherence, rel=1e-6) == 0.5
    # tag_memo_activation = coverage * coherence * (1 - noise) = 0.6 * 0.5 * 0.8 = 0.24
    assert pytest.approx(features.tag_memo_activation, rel=1e-6) == 0.24
    # novelty = residual_ratio*0.7 + directional_novelty*0.3 = 0.4*0.7 + 0.7*0.3 = 0.49
    assert pytest.approx(features.novelty, rel=1e-6) == 0.49


def test_handshake_disabled_returns_zero_coherence():
    """`use_handshake_features=False` → handshake=None → coherence=0 → tag_memo_activation=0."""
    dim = 4
    e = np.eye(dim, dtype=np.float32)
    rows = [_TagRow(i, f"t{i}", e[i]) for i in range(4)]
    query = (0.5 * e[0] + 0.5 * e[1]).astype(np.float32)

    pyramid = ResidualPyramid(
        rows, dim=dim, max_levels=2, top_k=2, use_handshake_features=False
    )
    result = pyramid.analyze(query)

    assert result.features.depth >= 1
    # No handshake → coherence stays 0 → tag_memo_activation = coverage * 0 = 0
    assert result.features.coherence == 0.0
    assert result.features.tag_memo_activation == 0.0
    assert result.levels[0].handshake_features is None


def test_analyze_dim_mismatch_raises():
    dim = 4
    rows = [_TagRow(0, "t0", np.eye(dim, dtype=np.float32)[0])]
    pyramid = ResidualPyramid(rows, dim=dim, max_levels=2, top_k=1)
    with pytest.raises(ValueError, match="expected query shape"):
        pyramid.analyze(np.zeros(dim + 1, dtype=np.float32))


def test_analyze_no_tags_returns_empty():
    dim = 4
    pyramid = ResidualPyramid([], dim=dim, max_levels=3, top_k=2)
    result = pyramid.analyze(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
    assert result.levels == ()
    assert result.features.depth == 0
    assert result.features.tag_memo_activation == 0.0


def test_analyze_avoids_reusing_tags_across_levels():
    """Once a tag has been picked at level-i, it should not appear again."""
    dim = 6
    basis = _make_orthogonal_basis(dim, 4)
    rows = [_TagRow(i, f"t{i}", basis[i]) for i in range(4)]
    # query = sum of all 4 basis vectors → each contributes equally
    query = sum(basis).astype(np.float32)

    pyramid = ResidualPyramid(rows, dim=dim, max_levels=3, top_k=2, min_energy_ratio=0.01)
    result = pyramid.analyze(query)

    # Collect all tag_ids across all levels — should be unique
    all_ids: list[int] = []
    for level in result.levels:
        all_ids.extend(t.tag_id for t in level.tags)
    assert len(all_ids) == len(set(all_ids))


def test_analyze_handshake_disabled_no_handshake_magnitudes():
    dim = 4
    e = np.eye(dim, dtype=np.float32)
    rows = [_TagRow(i, f"t{i}", e[i]) for i in range(4)]
    query = (0.5 * e[0] + 0.5 * e[1]).astype(np.float32)

    pyramid = ResidualPyramid(
        rows, dim=dim, max_levels=1, top_k=2, use_handshake_features=False
    )
    result = pyramid.analyze(query)
    assert all(t.handshake_magnitude == 0.0 for t in result.levels[0].tags)
