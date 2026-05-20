"""Tests for AppState.start_shadow_rebuild — Slice 5 second half."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from tagmemorag.config import Settings, StorageConfig
from tagmemorag.embedder import HashingEmbedder
from tagmemorag.errors import RebuildInProgressError, ServiceError
from tagmemorag.indexgen import (
    INDEXGEN_META_SCHEMA_VERSION,
    GenerationStatus,
    KbMeta,
    ReadyGeneration,
    read_meta,
)
from tagmemorag.state import AppState


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


def _seed_g1_index(cfg: Settings, kb_name: str) -> None:
    """Pretend the KB has been migrated: write index.json with a g1 active entry."""
    kb_root = Path(cfg.storage.data_dir) / kb_name
    kb_root.mkdir(parents=True, exist_ok=True)
    g1 = ReadyGeneration(
        created_at="2026-05-17T10:00:00Z",
        swap_at="2026-05-17T10:00:00Z",
        retired_at=None,
        parser_version="default",
        chunker_version="legacy",
        embedding_model_id=cfg.model.effective_embedding_model_id,
        embedding_model_version=cfg.model.embedding_model_version,
        index_schema_version=int(cfg.storage.schema_version),
        chunk_count=0,
        build_id="g1-seeded",
    )
    meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name=kb_name,
        active_generation=1,
        shadow_generation=None,
        generations={1: g1},
    )
    (kb_root / "index.json").write_text(
        json.dumps(meta.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _wait_for_task(task, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if task.status in {"done", "failed", "cancelled"}:
            return
        time.sleep(0.02)
    raise AssertionError(f"task did not finish within {timeout}s; status={task.status}")


def test_start_shadow_rebuild_writes_to_g2_and_updates_index(tmp_path, shadow_settings, shadow_embedder):
    docs = _populate_docs(tmp_path)
    _seed_g1_index(shadow_settings, "kb-shadow")

    app = AppState()
    task = app.start_shadow_rebuild(
        docs,
        "kb-shadow",
        shadow_settings,
        target_versions={"embedding_model_version": "v2"},
        embedder=shadow_embedder,
    )
    _wait_for_task(task)
    assert task.status == "done"

    kb_root = Path(shadow_settings.storage.data_dir) / "kb-shadow"
    assert (kb_root / "g2" / "graph.json").is_file()
    assert (kb_root / "g2" / "vectors.npz").is_file()
    assert not (kb_root / "graph.json").exists()  # legacy root NOT polluted

    meta = read_meta(kb_root)
    assert meta is not None
    assert meta.active_generation == 1
    assert meta.shadow_generation == 2
    shadow = meta.get_shadow()
    assert shadow is not None
    assert shadow.status == GenerationStatus.READY
    assert shadow.progress == 1.0
    assert "embedding_model_version" in shadow.trigger_diff


def test_shadow_state_installed_into_appstate(tmp_path, shadow_settings, shadow_embedder):
    docs = _populate_docs(tmp_path)
    _seed_g1_index(shadow_settings, "kb-installed")

    app = AppState()
    task = app.start_shadow_rebuild(
        docs,
        "kb-installed",
        shadow_settings,
        embedder=shadow_embedder,
    )
    _wait_for_task(task)
    assert task.status == "done"

    shadow_state = app.get_shadow_kb("kb-installed")
    assert shadow_state is not None
    assert shadow_state.kb_name == "kb-installed"
    assert shadow_state.vectors.shape[0] == shadow_state.graph.number_of_nodes()


def test_active_reads_unaffected_by_shadow_build(tmp_path, shadow_settings, shadow_embedder):
    docs = _populate_docs(tmp_path)
    _seed_g1_index(shadow_settings, "kb-active")

    app = AppState()
    # Active state intentionally NOT loaded; we verify get_kb still rejects
    from tagmemorag.errors import KbNotLoadedError
    task = app.start_shadow_rebuild(
        docs, "kb-active", shadow_settings, embedder=shadow_embedder
    )
    _wait_for_task(task)
    assert task.status == "done"

    with pytest.raises(KbNotLoadedError):
        app.get_kb("kb-active")  # active still empty; shadow does not leak


def test_second_shadow_rebuild_rejected_when_one_in_progress(tmp_path, shadow_settings, shadow_embedder):
    docs = _populate_docs(tmp_path)
    _seed_g1_index(shadow_settings, "kb-conflict")

    app = AppState()
    task1 = app.start_shadow_rebuild(
        docs, "kb-conflict", shadow_settings, embedder=shadow_embedder
    )
    # Second call before the first finishes — race-prone but typical case is
    # ours, so we expect either 409-equivalent (ServiceError saying shadow
    # already in progress) OR the first to have already finished.
    try:
        app.start_shadow_rebuild(
            docs, "kb-conflict", shadow_settings, embedder=shadow_embedder
        )
        # If we got here, the first finished too fast. Then meta.shadow is None
        # again only after a swap; without swap our shadow stays in shadow slot,
        # which means the second call should still be rejected.
        # If we reached here without exception, that's a real bug.
        _wait_for_task(task1)
        assert False, "Expected second start_shadow_rebuild to be rejected"
    except (ServiceError, RebuildInProgressError):
        pass

    _wait_for_task(task1)


def test_shadow_rebuild_cancellation(tmp_path, shadow_settings, shadow_embedder):
    docs = _populate_docs(tmp_path)
    _seed_g1_index(shadow_settings, "kb-cancel")

    app = AppState()
    task = app.start_shadow_rebuild(
        docs, "kb-cancel", shadow_settings, embedder=shadow_embedder
    )
    # Request cancellation immediately
    task.cancel_requested = True
    _wait_for_task(task)
    # Cancellation may race with completion; either outcome is acceptable but
    # the index.json must reflect a terminal state.
    assert task.status in {"cancelled", "done"}

    kb_root = Path(shadow_settings.storage.data_dir) / "kb-cancel"
    meta = read_meta(kb_root)
    assert meta is not None
    if task.status == "cancelled":
        shadow = meta.get_shadow()
        assert shadow is not None
        assert shadow.status == GenerationStatus.FAILED
        assert shadow.error is not None


def test_shadow_rebuild_rejects_when_kb_not_migrated(tmp_path, shadow_settings, shadow_embedder):
    docs = _populate_docs(tmp_path)
    # Note: no _seed_g1_index — the KB has no index.json
    Path(shadow_settings.storage.data_dir).mkdir(parents=True, exist_ok=True)
    (Path(shadow_settings.storage.data_dir) / "kb-unmigrated").mkdir(parents=True, exist_ok=True)

    app = AppState()
    with pytest.raises(ServiceError, match="not been migrated"):
        app.start_shadow_rebuild(
            docs, "kb-unmigrated", shadow_settings, embedder=shadow_embedder
        )


def test_shadow_rebuild_progress_visible_in_index(tmp_path, shadow_settings, shadow_embedder):
    docs = _populate_docs(tmp_path)
    _seed_g1_index(shadow_settings, "kb-progress")

    app = AppState()
    task = app.start_shadow_rebuild(
        docs, "kb-progress", shadow_settings, embedder=shadow_embedder
    )
    _wait_for_task(task)
    assert task.status == "done"

    kb_root = Path(shadow_settings.storage.data_dir) / "kb-progress"
    meta = read_meta(kb_root)
    assert meta is not None
    shadow = meta.get_shadow()
    assert shadow is not None
    assert shadow.progress == 1.0
    assert shadow.status == GenerationStatus.READY
