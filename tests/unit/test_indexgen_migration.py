"""Tests for indexgen.migration — lazy idempotent migration to g1 layout."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tagmemorag.config import Settings
from tagmemorag.indexgen import (
    INDEXGEN_META_FILENAME,
    KbMeta,
    migrate_kb_to_g1_if_needed,
    read_meta,
)
from tagmemorag.indexgen.migration import (
    LEGACY_DIRS,
    LEGACY_FILES,
)


def _settings(tmp_path: Path) -> Settings:
    cfg = Settings()
    cfg.storage.data_dir = str(tmp_path)
    cfg.vector_store.provider = "npz"
    return cfg


def _populate_legacy_kb(kb_root: Path, *, with_anchors_dir: bool = False) -> None:
    kb_root.mkdir(parents=True, exist_ok=True)
    (kb_root / "graph.json").write_text(json.dumps({
        "nodes": [{"id": 1}, {"id": 2}, {"id": 3}],
        "meta": {"build_id": "20260517100000"},
    }), encoding="utf-8")
    (kb_root / "vectors.npz").write_bytes(b"\x00" * 16)
    (kb_root / "chunk_identity.json").write_text("{}", encoding="utf-8")
    (kb_root / "epa_basis.npz").write_bytes(b"\x00" * 8)
    (kb_root / "tag_embeddings.npz").write_bytes(b"\x00" * 8)
    if with_anchors_dir:
        anchors_dir = kb_root / "anchors"
        anchors_dir.mkdir()
        (anchors_dir / "a.json").write_text("{}", encoding="utf-8")
    (kb_root / "anchors.json").write_text("[]", encoding="utf-8")


def test_migration_initialises_empty_kb(tmp_path: Path):
    settings = _settings(tmp_path)
    kb_root = tmp_path / "default"
    kb_root.mkdir()

    result = migrate_kb_to_g1_if_needed(kb_root, settings)

    assert result["status"] == "empty_kb_initialised"
    meta = read_meta(kb_root)
    assert meta is not None
    assert meta.active_generation is None
    assert meta.shadow_generation is None


def test_migration_moves_legacy_files_into_g1(tmp_path: Path):
    settings = _settings(tmp_path)
    kb_root = tmp_path / "default"
    _populate_legacy_kb(kb_root)

    result = migrate_kb_to_g1_if_needed(kb_root, settings)

    assert result["status"] == "migrated"
    g1 = kb_root / "g1"
    assert g1.is_dir()
    for name in ("graph.json", "vectors.npz", "chunk_identity.json", "epa_basis.npz",
                 "tag_embeddings.npz", "anchors.json"):
        assert (g1 / name).exists(), f"{name} should be in g1/"
        assert not (kb_root / name).exists(), f"{name} should be moved out of root"
    meta = read_meta(kb_root)
    assert meta is not None
    assert meta.active_generation == 1
    g1_entry = meta.get_active()
    assert g1_entry is not None
    assert g1_entry.chunk_count == 3
    assert g1_entry.build_id == "20260517100000"


def test_migration_moves_anchors_directory(tmp_path: Path):
    settings = _settings(tmp_path)
    kb_root = tmp_path / "default"
    _populate_legacy_kb(kb_root, with_anchors_dir=True)
    # Remove anchors.json so only the dir form is present
    (kb_root / "anchors.json").unlink()

    result = migrate_kb_to_g1_if_needed(kb_root, settings)
    assert result["status"] == "migrated"
    assert (kb_root / "g1" / "anchors").is_dir()
    assert (kb_root / "g1" / "anchors" / "a.json").is_file()
    assert not (kb_root / "anchors").exists()


def test_migration_idempotent_after_full_migration(tmp_path: Path):
    settings = _settings(tmp_path)
    kb_root = tmp_path / "default"
    _populate_legacy_kb(kb_root)

    first = migrate_kb_to_g1_if_needed(kb_root, settings)
    assert first["status"] == "migrated"
    second = migrate_kb_to_g1_if_needed(kb_root, settings)
    assert second["status"] == "already_migrated"


def test_migration_resumes_partial_g1_state(tmp_path: Path):
    settings = _settings(tmp_path)
    kb_root = tmp_path / "default"
    _populate_legacy_kb(kb_root)

    # Simulate a crash after some files moved: pre-create g1/ and shift two files in.
    g1 = kb_root / "g1"
    g1.mkdir()
    import os
    os.rename(kb_root / "graph.json", g1 / "graph.json")
    os.rename(kb_root / "vectors.npz", g1 / "vectors.npz")
    # remaining legacy files still in root; meta.json absent → migration should resume

    result = migrate_kb_to_g1_if_needed(kb_root, settings)

    assert result["status"] == "migrated"
    for name in ("graph.json", "vectors.npz", "chunk_identity.json", "epa_basis.npz",
                 "tag_embeddings.npz"):
        assert (g1 / name).exists()
        assert not (kb_root / name).exists()


def test_migration_rejects_corrupt_dual_present_state(tmp_path: Path):
    settings = _settings(tmp_path)
    kb_root = tmp_path / "default"
    _populate_legacy_kb(kb_root)

    # Both copies present (corrupt): graph.json in root AND in g1/
    g1 = kb_root / "g1"
    g1.mkdir()
    (g1 / "graph.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="Migration corrupt"):
        migrate_kb_to_g1_if_needed(kb_root, settings)


def test_migration_qdrant_alias_skipped_for_npz(tmp_path: Path):
    settings = _settings(tmp_path)
    kb_root = tmp_path / "default"
    _populate_legacy_kb(kb_root)

    result = migrate_kb_to_g1_if_needed(kb_root, settings)
    assert result["qdrant_alias_attempted"] is False
    assert result["qdrant_alias_result"] == "skipped:not_qdrant"


def test_migration_qdrant_alias_attempted_for_qdrant(tmp_path: Path):
    settings = _settings(tmp_path)
    settings.vector_store.provider = "qdrant"
    settings.vector_store.qdrant_url = "http://fake-qdrant:6333"
    settings.vector_store.collection_prefix = "tmr"

    kb_root = tmp_path / "default"
    _populate_legacy_kb(kb_root)

    captured: dict[str, object] = {}

    class _FakeQdrantClient:
        def __init__(self, **kwargs):
            captured["init_kwargs"] = kwargs

        def update_collection_aliases(self, change_aliases_operations):
            captured["aliases"] = change_aliases_operations

    with patch.dict("sys.modules", {"qdrant_client": _make_fake_qdrant_module(_FakeQdrantClient)}):
        result = migrate_kb_to_g1_if_needed(kb_root, settings)

    assert result["qdrant_alias_attempted"] is True
    assert result["qdrant_alias_result"] == "alias_created"
    assert captured["init_kwargs"]["url"] == "http://fake-qdrant:6333"


def _make_fake_qdrant_module(client_cls):
    """Build a fake qdrant_client module + qdrant_client.models subpackage."""
    import types

    module = types.ModuleType("qdrant_client")
    module.QdrantClient = client_cls

    models = types.ModuleType("qdrant_client.models")

    class _CreateAlias:
        def __init__(self, *, collection_name, alias_name):
            self.collection_name = collection_name
            self.alias_name = alias_name

    class _CreateAliasOperation:
        def __init__(self, *, create_alias):
            self.create_alias = create_alias

    models.CreateAlias = _CreateAlias
    models.CreateAliasOperation = _CreateAliasOperation

    import sys
    sys.modules["qdrant_client.models"] = models
    return module
