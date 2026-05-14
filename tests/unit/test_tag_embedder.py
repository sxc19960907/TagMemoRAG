from __future__ import annotations

from typing import Sequence

import numpy as np
import pytest

from tagmemorag.errors import EmbeddingDimMismatchError
from tagmemorag.manual_registry import SQLiteManualRegistry
from tagmemorag.tag_embedder import embed_dirty_tags
from tagmemorag.tag_store import upsert_canonical_tag


class RecordingEmbedder:
    def __init__(self, *, dim: int = 4):
        self.dim = dim
        self.calls: list[list[str]] = []

    def encode_batch(self, texts: Sequence[str]) -> np.ndarray:
        self.calls.append(list(texts))
        vectors = []
        for index, _text in enumerate(texts, start=1):
            vector = np.zeros(self.dim, dtype=np.float32)
            vector[index % self.dim] = 1.0
            vectors.append(vector)
        return np.asarray(vectors, dtype=np.float32)


class WrongDimEmbedder:
    def encode_batch(self, texts: Sequence[str]) -> np.ndarray:
        return np.ones((len(texts), 3), dtype=np.float32)


def test_embed_dirty_tags_writes_vectors_and_is_idempotent(tmp_path):
    registry = SQLiteManualRegistry(tmp_path / "registry.sqlite3")
    embedder = RecordingEmbedder(dim=4)

    with registry.connection() as conn:
        upsert_canonical_tag(conn, "default", "maintenance")
        upsert_canonical_tag(conn, "default", "cleaning")

        first = embed_dirty_tags(conn, "default", embedder, expected_dim=4)
        rows = conn.execute(
            "SELECT name, vector, embedding_dim, embedded_at FROM tags ORDER BY name"
        ).fetchall()
        second = embed_dirty_tags(conn, "default", embedder, expected_dim=4)

    assert first == {"added": 2, "skipped": 0, "failed": 0}
    assert second == {"added": 0, "skipped": 2, "failed": 0}
    assert embedder.calls == [["cleaning", "maintenance"]]
    assert [row["name"] for row in rows] == ["cleaning", "maintenance"]
    assert all(row["embedding_dim"] == 4 for row in rows)
    assert all(row["embedded_at"] for row in rows)
    assert all(np.frombuffer(row["vector"], dtype=np.float32).shape == (4,) for row in rows)


def test_embed_dirty_tags_only_embeds_missing_vectors(tmp_path):
    registry = SQLiteManualRegistry(tmp_path / "registry.sqlite3")
    embedder = RecordingEmbedder(dim=2)

    with registry.connection() as conn:
        clean_id = upsert_canonical_tag(conn, "default", "cleaning")
        upsert_canonical_tag(conn, "default", "maintenance")
        existing = np.array([1.0, 0.0], dtype=np.float32).tobytes()
        conn.execute(
            "UPDATE tags SET vector=?, embedding_dim=?, embedded_at=? WHERE id=?",
            (existing, 2, "2026-05-14T00:00:00+00:00", clean_id),
        )

        report = embed_dirty_tags(conn, "default", embedder, expected_dim=2)
        rows = conn.execute("SELECT name, vector FROM tags ORDER BY name").fetchall()

    assert report == {"added": 1, "skipped": 1, "failed": 0}
    assert embedder.calls == [["maintenance"]]
    assert rows[0]["vector"] == existing


def test_embed_dirty_tags_rejects_dimension_mismatch(tmp_path):
    registry = SQLiteManualRegistry(tmp_path / "registry.sqlite3")

    with registry.connection() as conn:
        upsert_canonical_tag(conn, "default", "maintenance")

        with pytest.raises(EmbeddingDimMismatchError) as exc:
            embed_dirty_tags(conn, "default", WrongDimEmbedder(), expected_dim=4)

        row = conn.execute("SELECT vector, embedding_dim, embedded_at FROM tags").fetchone()

    assert exc.value.code == "EMBEDDING_FAILED"
    assert exc.value.detail == {"expected_dim": 4, "actual_dim": 3}
    assert row["vector"] is None
    assert row["embedding_dim"] is None
    assert row["embedded_at"] is None


def test_embed_dirty_tags_noops_for_empty_kb(tmp_path):
    registry = SQLiteManualRegistry(tmp_path / "registry.sqlite3")
    embedder = RecordingEmbedder(dim=4)

    with registry.connection() as conn:
        report = embed_dirty_tags(conn, "default", embedder, expected_dim=4)

    assert report == {"added": 0, "skipped": 0, "failed": 0}
    assert embedder.calls == []
