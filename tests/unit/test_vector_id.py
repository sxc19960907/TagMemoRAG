"""Tests for vector_point_id derivation (Architecture v2 § A1)."""

from __future__ import annotations

import pytest

from tagmemorag.vector_id import vector_point_id


def test_vector_point_id_is_deterministic():
    a = vector_point_id("sha256:abc", "bge-m3", "v1")
    b = vector_point_id("sha256:abc", "bge-m3", "v1")
    assert a == b


def test_vector_point_id_changes_with_embedder_version():
    base = vector_point_id("sha256:abc", "bge-m3", "v1")
    new_version = vector_point_id("sha256:abc", "bge-m3", "v1.1")
    assert base != new_version


def test_vector_point_id_changes_with_embedder_id():
    base = vector_point_id("sha256:abc", "bge-m3", "v1")
    new_model = vector_point_id("sha256:abc", "qwen3-embedding-8b", "v1")
    assert base != new_model


def test_vector_point_id_changes_with_chunk():
    a = vector_point_id("sha256:abc", "bge-m3", "v1")
    b = vector_point_id("sha256:def", "bge-m3", "v1")
    assert a != b


def test_vector_point_id_returns_uuid_string():
    import uuid as _uuid

    pid = vector_point_id("sha256:abc", "bge-m3", "v1")
    parsed = _uuid.UUID(pid)
    assert str(parsed) == pid


def test_vector_point_id_rejects_empty_inputs():
    with pytest.raises(ValueError):
        vector_point_id("", "bge-m3", "v1")
    with pytest.raises(ValueError):
        vector_point_id("sha256:abc", "", "v1")
    with pytest.raises(ValueError):
        vector_point_id("sha256:abc", "bge-m3", "")


def test_vector_point_id_does_not_collide_on_field_boundary_ambiguity():
    # If we naively concatenated without separators, ("ab", "c", "d") and ("a", "bc", "d") would collide.
    a = vector_point_id("ab", "c", "d")
    b = vector_point_id("a", "bc", "d")
    assert a != b
