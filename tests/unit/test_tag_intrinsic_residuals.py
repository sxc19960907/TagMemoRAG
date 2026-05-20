from __future__ import annotations

import sqlite3

import numpy as np
import pytest

from tagmemorag.manual_registry import create_registry
from tagmemorag.tag_cooccurrence import CooccurrenceMatrix
from tagmemorag.tag_intrinsic_residuals import (
    load_intrinsic_residuals_for_kb,
    train_intrinsic_residuals_for_kb,
)


def _insert_tag(conn: sqlite3.Connection, kb_name: str, name: str, vector: np.ndarray) -> int:
    v = np.asarray(vector, dtype=np.float32)
    conn.execute(
        "INSERT INTO tags(kb_name, name, vector, embedding_dim, embedded_at) VALUES (?, ?, ?, ?, ?)",
        (kb_name, name, v.tobytes(), int(v.shape[0]), "2026-05-16"),
    )
    return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])


def test_train_intrinsic_residuals_computes_outside_neighbor_subspace(tmp_path):
    registry = create_registry(tmp_path / "registry.sqlite3")
    with registry.connection() as conn:
        a = _insert_tag(conn, "kb", "a", np.array([1.0, 1.0, 0.0], dtype=np.float32))
        b = _insert_tag(conn, "kb", "b", np.array([1.0, 0.0, 0.0], dtype=np.float32))
        c = _insert_tag(conn, "kb", "c", np.array([0.0, 1.0, 0.0], dtype=np.float32))
        matrix = CooccurrenceMatrix(kb_name="kb", edges={a: {b: 2.0, c: 1.0}}, edge_count=2)

        report = train_intrinsic_residuals_for_kb("kb", conn, matrix, expected_dim=3, top_n=1)
        residuals = load_intrinsic_residuals_for_kb(conn, "kb")

    assert report.rows_written == 3
    # Top-1 keeps only b, so half of a's energy remains outside the basis.
    assert residuals[a] == pytest.approx(0.5)
    # Incoming edges are valid neighbors too: b sees a as its basis.
    assert residuals[b] == pytest.approx(0.5)
    assert residuals[c] == pytest.approx(0.5)


def test_train_intrinsic_residuals_uses_incoming_edges_and_top_n(tmp_path):
    registry = create_registry(tmp_path / "registry.sqlite3")
    with registry.connection() as conn:
        target = _insert_tag(conn, "kb", "target", np.array([1.0, 1.0, 0.0], dtype=np.float32))
        weak = _insert_tag(conn, "kb", "weak", np.array([0.0, 1.0, 0.0], dtype=np.float32))
        strong = _insert_tag(conn, "kb", "strong", np.array([1.0, 0.0, 0.0], dtype=np.float32))
        matrix = CooccurrenceMatrix(
            kb_name="kb",
            edges={weak: {target: 0.1}, strong: {target: 3.0}},
            edge_count=2,
        )

        train_intrinsic_residuals_for_kb("kb", conn, matrix, expected_dim=3, top_n=1)
        residuals = load_intrinsic_residuals_for_kb(conn, "kb")
        row = conn.execute(
            "SELECT neighbor_count FROM tag_intrinsic_residuals WHERE tag_id=?", (target,)
        ).fetchone()

    assert residuals[target] == pytest.approx(0.5)
    assert int(row["neighbor_count"]) == 1
