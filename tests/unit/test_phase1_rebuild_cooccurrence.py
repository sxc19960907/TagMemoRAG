from __future__ import annotations

from pathlib import Path

import pytest

from tagmemorag.config import ManualLibraryConfig, Settings, StorageConfig, WavePhase1Config
from tagmemorag.manual_library import library_root, upsert_manual
from tagmemorag.state import build_kb
from tagmemorag.tag_cooccurrence import (
    cooccurrence_path,
    load_cooccurrence,
)
from tagmemorag import tag_rebuild as tag_rebuild_mod


def _cfg(tmp_path: Path, *, cooccurrence_enabled: bool = True) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(
            root_dir=str(tmp_path / "manuals"),
            registry_path=str(tmp_path / "manual_registry.sqlite3"),
        ),
        model={"dim": 64},
        wave_phase1=WavePhase1Config(cooccurrence_enabled=cooccurrence_enabled),
    )


def _metadata(source_file: str, manual_id: str, tags: list[str]) -> dict[str, object]:
    return {
        "manual_id": manual_id,
        "title": manual_id,
        "source_file": source_file,
        "product_category": "coffee",
        "tags": tags,
    }


def test_full_build_writes_cooccurrence_npz(tmp_path: Path, fake_embedder):
    cfg = _cfg(tmp_path)
    upsert_manual("default", _metadata("c/m1.md", "m1", ["Steam", "Wand"]), b"# m1\nclean.\n", cfg)
    upsert_manual("default", _metadata("c/m2.md", "m2", ["Steam", "Wand"]), b"# m2\nclean.\n", cfg)

    state = build_kb(library_root("default", cfg), "default", cfg, embedder=fake_embedder)

    matrix_path = cooccurrence_path(cfg, "default")
    assert matrix_path.exists(), "cooccurrence matrix should be written for non-empty manual_tags"
    matrix = load_cooccurrence(matrix_path)
    assert matrix is not None
    assert matrix.kb_name == "default"
    assert matrix.edge_count > 0
    assert state.meta["tag_cooccurrence_edges"] == matrix.edge_count
    assert state.meta["tag_cooccurrence_error"] == ""
    assert state.meta["tag_intrinsic_residual_rows"] > 0
    assert state.meta["tag_intrinsic_residual_error"] == ""


def test_intrinsic_residual_failure_does_not_break_rebuild(tmp_path: Path, fake_embedder, monkeypatch):
    cfg = _cfg(tmp_path)
    upsert_manual("default", _metadata("c/m1.md", "m1", ["Steam", "Wand"]), b"# m1\n", cfg)
    upsert_manual("default", _metadata("c/m2.md", "m2", ["Steam", "Wand"]), b"# m2\n", cfg)

    def boom(*args, **kwargs):
        raise RuntimeError("synthetic residual failure")

    monkeypatch.setattr(tag_rebuild_mod, "train_intrinsic_residuals_for_kb", boom)

    state = build_kb(library_root("default", cfg), "default", cfg, embedder=fake_embedder)

    assert state.graph.number_of_nodes() > 0
    assert state.meta["tag_cooccurrence_edges"] > 0
    assert state.meta["tag_intrinsic_residual_rows"] == 0
    assert state.meta["tag_intrinsic_residual_error"] == "RuntimeError"


def test_two_consecutive_builds_yield_identical_matrix(tmp_path: Path, fake_embedder):
    """AC6 anchor: rebuild N+1 produces same edges as rebuild N (modulo built_at)."""
    cfg = _cfg(tmp_path)
    upsert_manual("default", _metadata("c/m1.md", "m1", ["Steam", "Wand"]), b"# m1\nclean.\n", cfg)
    upsert_manual("default", _metadata("c/m2.md", "m2", ["Steam", "Wand"]), b"# m2\nclean.\n", cfg)

    build_kb(library_root("default", cfg), "default", cfg, embedder=fake_embedder)
    matrix_v1 = load_cooccurrence(cooccurrence_path(cfg, "default"))
    build_kb(library_root("default", cfg), "default", cfg, embedder=fake_embedder)
    matrix_v2 = load_cooccurrence(cooccurrence_path(cfg, "default"))

    assert matrix_v1 is not None and matrix_v2 is not None
    assert matrix_v1.edges == matrix_v2.edges
    assert matrix_v1.edge_count == matrix_v2.edge_count


def test_cooccurrence_disabled_skips_build(tmp_path: Path, fake_embedder):
    cfg = _cfg(tmp_path, cooccurrence_enabled=False)
    upsert_manual("default", _metadata("c/m1.md", "m1", ["Steam", "Wand"]), b"# m1\n", cfg)
    upsert_manual("default", _metadata("c/m2.md", "m2", ["Steam", "Wand"]), b"# m2\n", cfg)

    state = build_kb(library_root("default", cfg), "default", cfg, embedder=fake_embedder)

    matrix_path = cooccurrence_path(cfg, "default")
    assert not matrix_path.exists()
    assert state.meta["tag_cooccurrence_edges"] == 0
    assert state.meta["tag_cooccurrence_error"] == ""


def test_empty_manual_tags_does_not_write_file(tmp_path: Path, fake_embedder):
    """A KB with only single-tag manuals (n<2 guard) produces empty matrix → no file."""
    cfg = _cfg(tmp_path)
    upsert_manual("default", _metadata("c/m1.md", "m1", ["Steam"]), b"# m1\n", cfg)

    state = build_kb(library_root("default", cfg), "default", cfg, embedder=fake_embedder)

    matrix_path = cooccurrence_path(cfg, "default")
    assert not matrix_path.exists()
    assert state.meta["tag_cooccurrence_edges"] == 0
    assert state.meta["tag_cooccurrence_error"] == ""


def test_builder_failure_does_not_break_rebuild(tmp_path: Path, fake_embedder, monkeypatch):
    """AC10 anchor: cooccurrence build raises ⇒ rebuild still completes, error_type recorded."""
    cfg = _cfg(tmp_path)
    upsert_manual("default", _metadata("c/m1.md", "m1", ["Steam", "Wand"]), b"# m1\n", cfg)
    upsert_manual("default", _metadata("c/m2.md", "m2", ["Steam", "Wand"]), b"# m2\n", cfg)

    def boom(*args, **kwargs):
        raise RuntimeError("synthetic builder failure")

    monkeypatch.setattr(tag_rebuild_mod, "build_cooccurrence_for_kb", boom)

    state = build_kb(library_root("default", cfg), "default", cfg, embedder=fake_embedder)

    matrix_path = cooccurrence_path(cfg, "default")
    assert not matrix_path.exists()
    assert state.meta["tag_cooccurrence_edges"] == 0
    assert state.meta["tag_cooccurrence_error"] == "RuntimeError"
    # The rebuild still produced a state with chunks
    assert state.graph.number_of_nodes() > 0


def test_recovery_after_failure(tmp_path: Path, fake_embedder, monkeypatch):
    """After a failed cooccurrence build, the next rebuild repairs the matrix."""
    cfg = _cfg(tmp_path)
    upsert_manual("default", _metadata("c/m1.md", "m1", ["Steam", "Wand"]), b"# m1\n", cfg)
    upsert_manual("default", _metadata("c/m2.md", "m2", ["Steam", "Wand"]), b"# m2\n", cfg)

    def boom(*args, **kwargs):
        raise RuntimeError("synthetic builder failure")

    monkeypatch.setattr(tag_rebuild_mod, "build_cooccurrence_for_kb", boom)
    failed_state = build_kb(library_root("default", cfg), "default", cfg, embedder=fake_embedder)
    assert failed_state.meta["tag_cooccurrence_error"] == "RuntimeError"

    # Restore original builder
    monkeypatch.undo()
    repaired = build_kb(library_root("default", cfg), "default", cfg, embedder=fake_embedder)

    matrix_path = cooccurrence_path(cfg, "default")
    assert matrix_path.exists()
    assert repaired.meta["tag_cooccurrence_error"] == ""
    assert repaired.meta["tag_cooccurrence_edges"] > 0
