"""Vector point id derivation (Architecture v2 § A1).

Two-layer ID system:
- chunk_id: logical identity of a piece of text; embedder-agnostic.
- vector_point_id: identity of a chunk encoded by a specific embedder version.

Architecture rule: reranker_id never enters either id. Changing the reranker
must not invalidate stored vectors, chunks, or citations.
"""

from __future__ import annotations

import hashlib
import uuid


def vector_point_id(
    chunk_id: str,
    embedding_model_id: str,
    embedding_model_version: str,
) -> str:
    """Derive a deterministic UUID-shaped point id for a chunk + embedder pair.

    Returns a UUID string suitable for use as a Qdrant point id. Two different
    embedder versions encoding the same chunk produce two distinct ids; the
    same chunk re-embedded by the same version produces the same id.
    """
    if not chunk_id:
        raise ValueError("chunk_id must be non-empty")
    if not embedding_model_id:
        raise ValueError("embedding_model_id must be non-empty")
    if not embedding_model_version:
        raise ValueError("embedding_model_version must be non-empty")

    h = hashlib.sha256()
    h.update(chunk_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(embedding_model_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(embedding_model_version.encode("utf-8"))
    digest = h.digest()
    return str(uuid.UUID(bytes=digest[:16]))
