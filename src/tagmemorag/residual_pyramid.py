"""ResidualPyramid: multi-level Gram-Schmidt energy decomposition for query vectors.

Phase 2b-1 port of VCPToolBox's `Plugin/TagMemo/ResidualPyramid.js` (V3.7,
Physics-Optimized Edition). See `.trellis/tasks/05-15-wave-phase2b-residualpyramid/
research/source-residual-pyramid.md` for the source-walkthrough and the rationale
for the L2 (medium) port depth (Modified Gram-Schmidt + level-0 handshake +
full `tag_memo_activation = coverage * coherence * (1 - noise)` formula).

Pure algorithm: holds no DB / config / settings reference. Caller passes in
`tag_rows` (any object with `tag_id`, `name`, `vector` fields) at construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

import numpy as np


class _TagRowProto(Protocol):
    tag_id: int
    name: str
    vector: np.ndarray


@dataclass(frozen=True)
class PyramidTag:
    tag_id: int
    name: str
    similarity: float
    contribution: float
    handshake_magnitude: float = 0.0


@dataclass(frozen=True)
class HandshakeFeatures:
    direction_coherence: float
    pattern_strength: float
    novelty_signal: float
    noise_signal: float


@dataclass(frozen=True)
class PyramidLevel:
    level: int
    tags: tuple[PyramidTag, ...]
    projection_magnitude: float
    residual_magnitude: float
    residual_energy_ratio: float
    energy_explained: float
    handshake_features: HandshakeFeatures | None = None


@dataclass(frozen=True)
class PyramidFeatures:
    depth: int
    coverage: float
    novelty: float
    coherence: float
    tag_memo_activation: float
    expansion_signal: float


@dataclass(frozen=True)
class PyramidResult:
    levels: tuple[PyramidLevel, ...]
    total_explained_energy: float
    final_residual: np.ndarray
    features: PyramidFeatures


_EMPTY_FEATURES = PyramidFeatures(
    depth=0,
    coverage=0.0,
    novelty=1.0,
    coherence=0.0,
    tag_memo_activation=0.0,
    expansion_signal=1.0,
)


class ResidualPyramid:
    """Multi-level orthogonal projection of a query against tag vectors.

    Each level pulls top-K tag candidates by cosine similarity to the *current
    residual* (not the original query), runs Modified Gram-Schmidt to compute
    the orthogonal projection, and accumulates explained energy. Iteration
    stops when residual energy ratio drops below `min_energy_ratio` or when
    `max_levels` is reached.

    Level-0 additionally records "handshake" statistics (delta-vector direction
    coherence + pattern strength) used to derive `tag_memo_activation`.
    """

    def __init__(
        self,
        tag_rows: Sequence[_TagRowProto],
        *,
        dim: int,
        max_levels: int = 3,
        top_k: int = 10,
        min_energy_ratio: float = 0.1,
        use_handshake_features: bool = True,
    ) -> None:
        if dim <= 0:
            raise ValueError(f"dim must be positive; got {dim}")
        if max_levels < 1:
            raise ValueError(f"max_levels must be >= 1; got {max_levels}")
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1; got {top_k}")
        if not (0.0 < min_energy_ratio <= 1.0):
            raise ValueError(f"min_energy_ratio must be in (0,1]; got {min_energy_ratio}")

        self._tag_rows: list[_TagRowProto] = list(tag_rows)
        self._dim = int(dim)
        self._max_levels = int(max_levels)
        self._top_k = int(top_k)
        self._min_energy_ratio = float(min_energy_ratio)
        self._use_handshake_features = bool(use_handshake_features)

        # Pre-stack vectors for vectorized cosine
        if self._tag_rows:
            self._tag_matrix = np.stack(
                [np.asarray(row.vector, dtype=np.float32) for row in self._tag_rows]
            )
            norms = np.linalg.norm(self._tag_matrix, axis=1)
            # Avoid zero-norm rows in cosine; mark them so they get score 0
            self._tag_norms = np.where(norms < 1e-9, np.float32(1e-9), norms.astype(np.float32))
            self._tag_valid = norms >= 1e-9
        else:
            self._tag_matrix = np.zeros((0, self._dim), dtype=np.float32)
            self._tag_norms = np.zeros((0,), dtype=np.float32)
            self._tag_valid = np.zeros((0,), dtype=bool)

    @property
    def dim(self) -> int:
        return self._dim

    def analyze(self, query_vec: np.ndarray) -> PyramidResult:
        query = np.asarray(query_vec, dtype=np.float32)
        if query.shape != (self._dim,):
            raise ValueError(f"expected query shape ({self._dim},), got {query.shape}")

        original_magnitude = float(np.linalg.norm(query))
        original_energy = original_magnitude * original_magnitude
        if original_energy < 1e-12 or len(self._tag_rows) == 0:
            return PyramidResult(
                levels=(),
                total_explained_energy=0.0,
                final_residual=query.copy(),
                features=_EMPTY_FEATURES,
            )

        current_residual = query.copy()
        levels: list[PyramidLevel] = []
        total_explained = 0.0
        used_indices: set[int] = set()

        for level_idx in range(self._max_levels):
            candidates = self._topk_cosine(current_residual, used_indices)
            if not candidates:
                break

            tag_vectors = [self._tag_matrix[idx] for idx, _sim in candidates]
            projection, residual, basis_coeffs = _gram_schmidt_project(
                current_residual, tag_vectors
            )

            residual_magnitude = float(np.linalg.norm(residual))
            residual_energy = residual_magnitude * residual_magnitude
            current_energy = float(np.linalg.norm(current_residual)) ** 2
            energy_explained = max(0.0, current_energy - residual_energy) / original_energy

            handshake: HandshakeFeatures | None = None
            magnitudes: list[float] = [0.0] * len(candidates)
            if level_idx == 0 and self._use_handshake_features:
                magnitudes, directions = _compute_handshakes(query, tag_vectors)
                handshake = _analyze_handshakes(magnitudes, directions)

            tags = tuple(
                PyramidTag(
                    tag_id=int(self._tag_rows[idx].tag_id),
                    name=str(self._tag_rows[idx].name),
                    similarity=float(sim),
                    contribution=float(basis_coeffs[i]),
                    handshake_magnitude=float(magnitudes[i]) if level_idx == 0 and self._use_handshake_features else 0.0,
                )
                for i, (idx, sim) in enumerate(candidates)
            )
            levels.append(
                PyramidLevel(
                    level=level_idx,
                    tags=tags,
                    projection_magnitude=float(np.linalg.norm(projection)),
                    residual_magnitude=residual_magnitude,
                    residual_energy_ratio=residual_energy / original_energy,
                    energy_explained=energy_explained,
                    handshake_features=handshake,
                )
            )
            total_explained += energy_explained

            for idx, _sim in candidates:
                used_indices.add(idx)

            current_residual = residual
            if (residual_energy / original_energy) < self._min_energy_ratio:
                break

        features = _extract_features(levels, total_explained)
        return PyramidResult(
            levels=tuple(levels),
            total_explained_energy=float(total_explained),
            final_residual=current_residual,
            features=features,
        )

    def _topk_cosine(
        self,
        query: np.ndarray,
        exclude: set[int],
    ) -> list[tuple[int, float]]:
        if not self._tag_rows:
            return []
        q_norm = float(np.linalg.norm(query))
        if q_norm < 1e-9:
            return []
        # Vectorized cosine
        sims = (self._tag_matrix @ query) / (self._tag_norms * q_norm)
        # Mask invalid rows + already-used rows
        if exclude:
            mask = np.ones(len(self._tag_rows), dtype=bool)
            for idx in exclude:
                if 0 <= idx < len(mask):
                    mask[idx] = False
            mask &= self._tag_valid
        else:
            mask = self._tag_valid.copy()
        if not mask.any():
            return []
        sims_masked = np.where(mask, sims, -np.inf)
        # top-k by similarity, then by index for stability
        k = min(self._top_k, int(mask.sum()))
        if k <= 0:
            return []
        idx_sorted = np.argpartition(-sims_masked, k - 1)[:k]
        idx_sorted = idx_sorted[np.argsort(-sims_masked[idx_sorted], kind="stable")]
        return [(int(i), float(sims_masked[i])) for i in idx_sorted if np.isfinite(sims_masked[i])]


def _gram_schmidt_project(
    vector: np.ndarray,
    tag_vectors: Sequence[np.ndarray],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Modified Gram-Schmidt orthogonal projection (matches ResidualPyramid.js:160-207).

    Returns (projection, residual, basis_coefficients). `basis_coefficients[i]`
    is `|<query, u_i>|` where u_i is the orthonormalized i-th tag vector;
    linearly-dependent tags get coefficient 0.
    """
    dim = vector.shape[0]
    n = len(tag_vectors)
    basis: list[np.ndarray] = []
    coeffs = np.zeros(n, dtype=np.float32)

    for i, tv in enumerate(tag_vectors):
        v = np.asarray(tv, dtype=np.float32).copy()
        # Subtract projections onto existing basis
        for u in basis:
            v -= float(np.dot(v, u)) * u
        mag = float(np.linalg.norm(v))
        if mag > 1e-6:
            v = v / mag
            basis.append(v)
            coeffs[i] = abs(float(np.dot(vector, v)))
        # else: linearly dependent; coeffs[i] stays 0

    projection = np.zeros(dim, dtype=np.float32)
    for u in basis:
        projection += float(np.dot(vector, u)) * u
    residual = vector - projection
    return projection.astype(np.float32), residual.astype(np.float32), coeffs


def _compute_handshakes(
    query: np.ndarray,
    tag_vectors: Sequence[np.ndarray],
) -> tuple[list[float], list[np.ndarray]]:
    """Compute (magnitudes, directions) of `query - tag_i` deltas (ResidualPyramid.js:213-265)."""
    magnitudes: list[float] = []
    directions: list[np.ndarray] = []
    for tv in tag_vectors:
        delta = query - np.asarray(tv, dtype=np.float32)
        mag = float(np.linalg.norm(delta))
        magnitudes.append(mag)
        if mag > 1e-9:
            directions.append((delta / mag).astype(np.float32))
        else:
            directions.append(np.zeros_like(query))
    return magnitudes, directions


def _analyze_handshakes(
    magnitudes: list[float],
    directions: list[np.ndarray],
) -> HandshakeFeatures:
    """Statistics over delta-vector directions (ResidualPyramid.js:271-312)."""
    n = len(directions)
    if n == 0:
        return HandshakeFeatures(0.0, 0.0, 0.0, 0.0)
    avg_direction = np.mean(np.stack(directions), axis=0)
    direction_coherence = float(np.linalg.norm(avg_direction))
    # Pairwise sim over the first 5 (matches source's O(N^2) cap)
    limit = min(n, 5)
    pairs: list[float] = []
    for i in range(limit):
        for j in range(i + 1, limit):
            pairs.append(abs(float(np.dot(directions[i], directions[j]))))
    pattern_strength = float(np.mean(pairs)) if pairs else 0.0
    novelty_signal = direction_coherence
    noise_signal = (1.0 - direction_coherence) * (1.0 - pattern_strength)
    return HandshakeFeatures(
        direction_coherence=direction_coherence,
        pattern_strength=pattern_strength,
        novelty_signal=novelty_signal,
        noise_signal=noise_signal,
    )


def _extract_features(
    levels: list[PyramidLevel],
    total_explained_energy: float,
) -> PyramidFeatures:
    """Derive scalar features from pyramid levels (ResidualPyramid.js:317-352)."""
    if not levels:
        return _EMPTY_FEATURES
    handshake = levels[0].handshake_features
    coverage = min(1.0, max(0.0, total_explained_energy))
    coherence = handshake.pattern_strength if handshake is not None else 0.0
    residual_ratio = 1.0 - coverage
    directional_novelty = handshake.novelty_signal if handshake is not None else 0.0
    novelty = residual_ratio * 0.7 + directional_novelty * 0.3
    noise = handshake.noise_signal if handshake is not None else 0.0
    tag_memo_activation = max(0.0, coverage * coherence * (1.0 - noise))
    return PyramidFeatures(
        depth=len(levels),
        coverage=float(coverage),
        novelty=float(novelty),
        coherence=float(coherence),
        tag_memo_activation=float(tag_memo_activation),
        expansion_signal=float(novelty),
    )
