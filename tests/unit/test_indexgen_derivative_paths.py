from __future__ import annotations

from pathlib import Path

from tagmemorag.config import Settings
from tagmemorag.epa_basis import basis_dirty_path, basis_lock_path, basis_path, mark_epa_basis_dirty
from tagmemorag.indexgen import KbPaths
from tagmemorag.tag_cooccurrence import CooccurrenceMatrix, cooccurrence_path, load_cooccurrence, save_cooccurrence


def _settings(tmp_path: Path) -> Settings:
    cfg = Settings()
    cfg.storage.data_dir = str(tmp_path)
    return cfg


def test_epa_basis_paths_are_legacy_by_default_and_generation_aware_with_paths(tmp_path):
    cfg = _settings(tmp_path)
    paths = KbPaths("default", cfg, generation=2)

    assert basis_path(cfg) == tmp_path / "_global" / "epa_basis.npz"
    assert basis_lock_path(cfg) == tmp_path / "_global" / "epa_basis.lock"
    assert basis_dirty_path(cfg) == tmp_path / "_global" / "epa_basis.dirty"
    assert basis_path(cfg, paths) == tmp_path / "default" / "g2" / "epa_basis.npz"
    assert basis_lock_path(cfg, paths) == tmp_path / "default" / "g2" / "epa_basis.lock"
    assert basis_dirty_path(cfg, paths) == tmp_path / "default" / "g2" / "epa_basis.dirty"


def test_mark_epa_basis_dirty_can_target_generation_path(tmp_path):
    cfg = _settings(tmp_path)
    paths = KbPaths("default", cfg, generation=3)

    mark_epa_basis_dirty(cfg, paths)

    assert (tmp_path / "default" / "g3" / "epa_basis.dirty").exists()
    assert not (tmp_path / "_global" / "epa_basis.dirty").exists()


def test_cooccurrence_can_round_trip_in_generation_path(tmp_path):
    cfg = _settings(tmp_path)
    paths = KbPaths("default", cfg, generation=4)
    matrix = CooccurrenceMatrix(kb_name="default", edges={1: {2: 0.7}}, edge_count=1)

    save_cooccurrence(paths.tag_cooccurrence, matrix)
    loaded = load_cooccurrence(paths.tag_cooccurrence)

    assert paths.tag_cooccurrence == tmp_path / "default" / "g4" / "tag_cooccurrence.npz"
    assert cooccurrence_path(cfg, "default") == tmp_path / "_global" / "tag_cooccurrence" / "default.npz"
    assert loaded is not None
    assert loaded.edges == {1: {2: 0.699999988079071}}
