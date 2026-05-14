from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Any

import numpy as np

from .errors import EmbeddingDimMismatchError


def embed_dirty_tags(
    conn: sqlite3.Connection,
    kb_name: str,
    embedder: Any,
    *,
    expected_dim: int | None = None,
) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT id, name, vector
        FROM tags
        WHERE kb_name=?
        ORDER BY name, id
        """,
        (kb_name,),
    ).fetchall()
    dirty = [row for row in rows if row["vector"] is None]
    skipped = len(rows) - len(dirty)
    if not dirty:
        return {"added": 0, "skipped": skipped, "failed": 0}

    names = [str(row["name"]) for row in dirty]
    vectors = np.asarray(embedder.encode_batch(names), dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[0] != len(dirty):
        raise EmbeddingDimMismatchError(expected_dim or 0, int(vectors.shape[1]) if vectors.ndim == 2 else 0)
    actual_dim = int(vectors.shape[1])
    if expected_dim is not None and actual_dim != expected_dim:
        raise EmbeddingDimMismatchError(expected_dim, actual_dim)

    embedded_at = datetime.now(timezone.utc).isoformat()
    with conn:
        for row, vector in zip(dirty, vectors, strict=True):
            conn.execute(
                """
                UPDATE tags
                SET vector=?, embedding_dim=?, embedded_at=?
                WHERE id=?
                """,
                (np.asarray(vector, dtype=np.float32).tobytes(), actual_dim, embedded_at, int(row["id"])),
            )
    return {"added": len(dirty), "skipped": skipped, "failed": 0}
