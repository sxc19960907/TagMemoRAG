"""Tests for indexgen.shadow_build.build_shadow_kb."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tagmemorag.config import Settings, StorageConfig
from tagmemorag.embedder import HashingEmbedder
from tagmemorag.indexgen import KbPaths, build_shadow_kb


@pytest.fixture
def shadow_settings(tmp_path: Path) -> Settings:
    return Settings(storage=StorageConfig(data_dir=str(tmp_path / "data")), model={"dim": 64})


@pytest.fixture
def shadow_embedder() -> HashingEmbedder:
    return HashingEmbedder(dim=64)


def _populate_docs(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual_a.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    (docs / "manual_b.md").write_text("# 维护\n清洁滤网每月一次。\n", encoding="utf-8")
    return docs


def test_build_shadow_writes_to_generation_directory(tmp_path, shadow_settings, shadow_embedder):
    docs = _populate_docs(tmp_path)
    paths = KbPaths("kb-shadow", shadow_settings, generation=2)

    state = build_shadow_kb(
        docs,
        "kb-shadow",
        shadow_settings,
        paths=paths,
        embedder=shadow_embedder,
    )

    assert state.kb_name == "kb-shadow"
    assert state.vectors.shape[0] == state.graph.number_of_nodes()
    assert paths.generation_root.is_dir()
    assert paths.graph.is_file()
    assert paths.vectors.is_file()
    assert paths.chunk_identity.is_file()
    assert paths.anchors.is_file()
    assert paths.meta.is_file()


def test_build_shadow_does_not_pollute_active_kb_root(tmp_path, shadow_settings, shadow_embedder):
    docs = _populate_docs(tmp_path)
    paths = KbPaths("kb-iso", shadow_settings, generation=2)

    build_shadow_kb(
        docs, "kb-iso", shadow_settings, paths=paths, embedder=shadow_embedder
    )

    kb_root = paths.kb_root
    # Direct kb_root should NOT contain the products — only the g2/ subdir
    for filename in ("graph.json", "vectors.npz", "chunk_identity.json", "anchors.json", "meta.json"):
        assert not (kb_root / filename).exists(), f"shadow leaked {filename} into kb_root"


def test_build_shadow_writes_index_json_unchanged(tmp_path, shadow_settings, shadow_embedder):
    """Shadow build must not touch index.json (the IndexGeneration index)."""
    docs = _populate_docs(tmp_path)
    paths = KbPaths("kb-noindex", shadow_settings, generation=2)
    paths.kb_root.mkdir(parents=True)
    sentinel = {"sentinel": "do not touch"}
    paths.index_json.write_text(json.dumps(sentinel), encoding="utf-8")

    build_shadow_kb(
        docs, "kb-noindex", shadow_settings, paths=paths, embedder=shadow_embedder
    )

    assert json.loads(paths.index_json.read_text(encoding="utf-8")) == sentinel


def test_build_shadow_progress_callback_invoked(tmp_path, shadow_settings, shadow_embedder):
    docs = _populate_docs(tmp_path)
    paths = KbPaths("kb-progress", shadow_settings, generation=3)
    captured: list[tuple[float, str]] = []

    def cb(progress: float, stage: str) -> None:
        captured.append((progress, stage))

    build_shadow_kb(
        docs,
        "kb-progress",
        shadow_settings,
        paths=paths,
        embedder=shadow_embedder,
        progress_cb=cb,
    )

    assert captured, "progress_cb should be invoked at least once"
    progresses = [p for p, _ in captured]
    assert progresses[0] == 0.0
    assert progresses[-1] == 1.0
    assert progresses == sorted(progresses), "progress must be monotonic"
    stages = {stage for _, stage in captured}
    assert {"init", "embed", "graph", "save", "done"}.issubset(stages)


def test_build_shadow_target_versions_overlay_does_not_mutate_input(
    tmp_path, shadow_settings, shadow_embedder
):
    docs = _populate_docs(tmp_path)
    paths = KbPaths("kb-overlay", shadow_settings, generation=2)
    original_id = shadow_settings.model.embedding_model_id
    original_version = shadow_settings.model.embedding_model_version

    build_shadow_kb(
        docs,
        "kb-overlay",
        shadow_settings,
        paths=paths,
        target_versions={
            "embedding_model_id": "qwen3-embedding-8b",
            "embedding_model_version": "v1.5",
        },
        embedder=shadow_embedder,
    )

    # active_cfg untouched after the call
    assert shadow_settings.model.embedding_model_id == original_id
    assert shadow_settings.model.embedding_model_version == original_version


def test_build_shadow_writes_embedder_id_into_meta(tmp_path, shadow_settings, shadow_embedder):
    docs = _populate_docs(tmp_path)
    paths = KbPaths("kb-meta", shadow_settings, generation=2)

    build_shadow_kb(
        docs,
        "kb-meta",
        shadow_settings,
        paths=paths,
        target_versions={
            "embedding_model_id": "qwen3-embedding-8b",
            "embedding_model_version": "v1.5",
        },
        embedder=shadow_embedder,
    )

    meta = json.loads(paths.meta.read_text(encoding="utf-8"))
    assert meta["embedding_model_id"] == "qwen3-embedding-8b"
    assert meta["embedding_model_version"] == "v1.5"
    assert meta["shadow_build"] is True


def test_build_shadow_legacy_mode_writes_to_kb_root(tmp_path, shadow_settings, shadow_embedder):
    """If KbPaths is constructed in legacy mode (generation=None), shadow build writes at kb_root.

    This isn't a normal usage but proves the function is path-injection-pure.
    """
    docs = _populate_docs(tmp_path)
    paths = KbPaths("kb-legacy", shadow_settings)  # legacy mode

    build_shadow_kb(
        docs, "kb-legacy", shadow_settings, paths=paths, embedder=shadow_embedder
    )

    assert paths.graph == paths.kb_root / "graph.json"
    assert paths.graph.is_file()


def test_build_shadow_handles_empty_docs(tmp_path, shadow_settings, shadow_embedder):
    docs = tmp_path / "empty"
    docs.mkdir()
    paths = KbPaths("kb-empty", shadow_settings, generation=2)

    state = build_shadow_kb(
        docs, "kb-empty", shadow_settings, paths=paths, embedder=shadow_embedder
    )

    assert state.vectors.shape == (0, shadow_settings.model.dim)
    assert state.graph.number_of_nodes() == 0
    assert paths.graph.is_file()


def test_build_shadow_raises_when_docs_missing(tmp_path, shadow_settings, shadow_embedder):
    paths = KbPaths("kb-missing", shadow_settings, generation=2)
    from tagmemorag.errors import RebuildFailedError

    with pytest.raises(RebuildFailedError):
        build_shadow_kb(
            tmp_path / "nonexistent",
            "kb-missing",
            shadow_settings,
            paths=paths,
            embedder=shadow_embedder,
        )
