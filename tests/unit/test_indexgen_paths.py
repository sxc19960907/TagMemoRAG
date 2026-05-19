"""Tests for indexgen.paths.KbPaths — generation-aware product path helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from tagmemorag.config import Settings
from tagmemorag.indexgen import KbPaths


def _settings(tmp_path: Path) -> Settings:
    cfg = Settings()
    cfg.storage.data_dir = str(tmp_path)
    return cfg


def test_legacy_mode_paths_match_existing_layout(tmp_path: Path):
    cfg = _settings(tmp_path)
    paths = KbPaths("default", cfg)

    expected_root = tmp_path / "default"
    assert paths.kb_root == expected_root
    assert paths.generation_root == expected_root  # legacy: same as kb_root
    assert paths.graph == expected_root / "graph.json"
    assert paths.vectors == expected_root / "vectors.npz"
    assert paths.chunk_identity == expected_root / "chunk_identity.json"
    assert paths.anchors == expected_root / "anchors.json"
    assert paths.anchors_dir == expected_root / "anchors"
    assert paths.epa_basis == expected_root / "epa_basis.npz"
    assert paths.tag_embeddings == expected_root / "tag_embeddings.npz"
    assert paths.tag_cooccurrence == expected_root / "tag_cooccurrence.npz"
    assert paths.tag_intrinsic_residuals == expected_root / "tag_intrinsic_residuals.npz"
    assert paths.rebuild_impact == expected_root / "rebuild_impact.json"
    assert paths.meta == expected_root / "meta.json"
    assert paths.assets_root == expected_root / "assets"


def test_generation_mode_routes_under_g_n(tmp_path: Path):
    cfg = _settings(tmp_path)
    paths = KbPaths("default", cfg, generation=2)

    expected_gen_root = tmp_path / "default" / "g2"
    assert paths.kb_root == tmp_path / "default"  # kb_root unchanged
    assert paths.generation_root == expected_gen_root
    assert paths.graph == expected_gen_root / "graph.json"
    assert paths.vectors == expected_gen_root / "vectors.npz"
    assert paths.chunk_identity == expected_gen_root / "chunk_identity.json"
    assert paths.anchors == expected_gen_root / "anchors.json"
    assert paths.epa_basis == expected_gen_root / "epa_basis.npz"
    assert paths.tag_embeddings == expected_gen_root / "tag_embeddings.npz"
    assert paths.tag_cooccurrence == expected_gen_root / "tag_cooccurrence.npz"
    assert paths.tag_intrinsic_residuals == expected_gen_root / "tag_intrinsic_residuals.npz"
    assert paths.meta == expected_gen_root / "meta.json"
    assert paths.assets_root == expected_gen_root / "assets"


def test_index_json_always_at_kb_root(tmp_path: Path):
    """index.json is the IndexGeneration index; it lives at kb_root regardless of mode."""
    cfg = _settings(tmp_path)
    legacy = KbPaths("default", cfg)
    g1 = KbPaths("default", cfg, generation=1)
    g2 = KbPaths("default", cfg, generation=2)

    expected = tmp_path / "default" / "index.json"
    assert legacy.index_json == expected
    assert g1.index_json == expected
    assert g2.index_json == expected


def test_ensure_generation_root_creates_dir(tmp_path: Path):
    cfg = _settings(tmp_path)
    paths = KbPaths("kb-x", cfg, generation=3)
    target = paths.ensure_generation_root()
    assert target == tmp_path / "kb-x" / "g3"
    assert target.is_dir()


def test_ensure_generation_root_idempotent(tmp_path: Path):
    cfg = _settings(tmp_path)
    paths = KbPaths("kb-x", cfg, generation=3)
    paths.ensure_generation_root()
    # second call must not raise
    again = paths.ensure_generation_root()
    assert again.is_dir()


def test_ensure_generation_root_in_legacy_mode_creates_kb_root(tmp_path: Path):
    cfg = _settings(tmp_path)
    paths = KbPaths("kb-y", cfg)
    target = paths.ensure_generation_root()
    assert target == tmp_path / "kb-y"
    assert target.is_dir()


def test_paths_are_pure_no_filesystem_side_effects(tmp_path: Path):
    """Reading any path attribute must not touch the filesystem."""
    cfg = _settings(tmp_path)
    paths = KbPaths("kb-untouched", cfg, generation=42)
    # Access many attributes
    _ = (paths.graph, paths.vectors, paths.chunk_identity, paths.anchors,
         paths.epa_basis, paths.tag_embeddings, paths.meta, paths.index_json)
    # Filesystem must remain untouched
    assert not (tmp_path / "kb-untouched").exists()


def test_per_kb_isolation(tmp_path: Path):
    cfg = _settings(tmp_path)
    a = KbPaths("kb-a", cfg, generation=1)
    b = KbPaths("kb-b", cfg, generation=1)
    assert a.graph != b.graph
    assert a.kb_root != b.kb_root


def test_generation_must_be_int_when_provided(tmp_path: Path):
    cfg = _settings(tmp_path)
    paths = KbPaths("kb-z", cfg, generation=5)
    assert paths.generation_root.name == "g5"
