from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from typing import Mapping

import numpy as np

from .residual_pyramid import _gram_schmidt_project
from .tag_cooccurrence import CooccurrenceMatrix
from .tag_store import iter_canonical_tags_with_vectors


@dataclass(frozen=True)
class IntrinsicResidualTrainReport:
    rows_written: int = 0
    skipped_tags: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "tag_intrinsic_residual_rows": int(self.rows_written),
            "tag_intrinsic_residual_skipped": int(self.skipped_tags),
        }


def train_intrinsic_residuals_for_kb(
    kb_name: str,
    conn: sqlite3.Connection,
    matrix: CooccurrenceMatrix,
    *,
    expected_dim: int,
    top_n: int,
) -> IntrinsicResidualTrainReport:
    if expected_dim <= 0:
        raise ValueError(f"expected_dim must be positive; got {expected_dim}")
    if top_n <= 0:
        raise ValueError(f"top_n must be positive; got {top_n}")

    vectors: dict[int, np.ndarray] = {}
    for tag in iter_canonical_tags_with_vectors(conn, kb_name=kb_name):
        if tag.vector is None or tag.embedding_dim != expected_dim:
            continue
        vector = np.frombuffer(tag.vector, dtype=np.float32)
        if vector.shape == (expected_dim,):
            vectors[int(tag.id)] = np.asarray(vector, dtype=np.float32)

    now = datetime.now(timezone.utc).isoformat()
    rows_written = 0
    skipped = 0
    with conn:
        for tag_id in sorted(vectors):
            vector = vectors[tag_id]
            neighbor_ids = _top_neighbor_ids(matrix, tag_id, top_n)
            neighbor_vectors = [vectors[nid] for nid in neighbor_ids if nid in vectors]
            if not neighbor_vectors:
                residual_energy = 1.0
                neighbor_count = 0
                skipped += 1
            else:
                residual_energy = _residual_energy(vector, neighbor_vectors)
                neighbor_count = len(neighbor_vectors)
            conn.execute(
                """
                INSERT INTO tag_intrinsic_residuals(tag_id, residual_energy, neighbor_count, computed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tag_id) DO UPDATE SET
                    residual_energy=excluded.residual_energy,
                    neighbor_count=excluded.neighbor_count,
                    computed_at=excluded.computed_at
                """,
                (tag_id, residual_energy, neighbor_count, now),
            )
            rows_written += 1
    return IntrinsicResidualTrainReport(rows_written=rows_written, skipped_tags=skipped)


def load_intrinsic_residuals_for_kb(
    conn: sqlite3.Connection,
    kb_name: str,
) -> dict[int, float]:
    rows = conn.execute(
        """
        SELECT t.id, r.residual_energy
        FROM tags t
        JOIN tag_intrinsic_residuals r ON r.tag_id = t.id
        WHERE t.kb_name = ?
        ORDER BY t.id
        """,
        (kb_name,),
    ).fetchall()
    return {int(row["id"]): float(row["residual_energy"]) for row in rows}


def missing_residual_count(tag_ids: Mapping[int, object] | set[int], residuals: Mapping[int, float]) -> int:
    return sum(1 for tag_id in tag_ids if int(tag_id) not in residuals)


def _top_neighbor_ids(matrix: CooccurrenceMatrix, tag_id: int, top_n: int) -> list[int]:
    weights: dict[int, float] = {}
    for dst, weight in matrix.neighbors(tag_id).items():
        weights[int(dst)] = max(weights.get(int(dst), 0.0), float(weight))
    for src, targets in matrix.edges.items():
        if int(tag_id) in targets:
            weights[int(src)] = max(weights.get(int(src), 0.0), float(targets[int(tag_id)]))
    weights.pop(int(tag_id), None)
    return [
        neighbor_id
        for neighbor_id, _weight in sorted(weights.items(), key=lambda kv: (-float(kv[1]), int(kv[0])))[:top_n]
    ]


def _residual_energy(vector: np.ndarray, neighbor_vectors: list[np.ndarray]) -> float:
    original_energy = float(np.dot(vector, vector))
    if original_energy < 1e-12:
        return 1.0
    _projection, residual, _coeffs = _gram_schmidt_project(vector, neighbor_vectors)
    energy = float(np.dot(residual, residual)) / original_energy
    return max(0.0, min(1.0, energy))
