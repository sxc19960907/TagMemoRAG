"""Tests for AppState.swap_generation / retire_generation — Slice 6."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tagmemorag.config import Settings, StorageConfig
from tagmemorag.embedder import HashingEmbedder
from tagmemorag.errors import ErrorCode, ServiceError
from tagmemorag.indexgen import (
    INDEXGEN_META_SCHEMA_VERSION,
    GenerationStatus,
    KbMeta,
    ReadyGeneration,
    read_meta,
    write_meta,
)
from tagmemorag.state import AppState


@pytest.fixture
def s_settings(tmp_path: Path) -> Settings:
    return Settings(storage=StorageConfig(data_dir=str(tmp_path / "data")), model={"dim": 64})


@pytest.fixture
def s_embedder() -> HashingEmbedder:
    return HashingEmbedder(dim=64)


def _docs(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual_a.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    return docs


def _seed_index(cfg: Settings, kb_name: str) -> None:
    from datetime import datetime, timezone

    kb_root = Path(cfg.storage.data_dir) / kb_name
    kb_root.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    g1 = ReadyGeneration(
        created_at=now_iso,
        swap_at=now_iso,
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


def _wait_for(task, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if task.status in {"done", "failed", "cancelled"}:
            return
        time.sleep(0.02)
    raise AssertionError(f"task did not finish; status={task.status}")


def _do_shadow_build(app: AppState, docs: Path, kb_name: str, cfg: Settings, embedder, **kw):
    task = app.start_shadow_rebuild(docs, kb_name, cfg, embedder=embedder, **kw)
    _wait_for(task)
    assert task.status == "done", f"shadow build did not complete cleanly: {task.error}"


# ============== swap_generation ==============

def test_swap_promotes_shadow_to_active(tmp_path, s_settings, s_embedder):
    docs = _docs(tmp_path)
    _seed_index(s_settings, "kb-swap")

    app = AppState()
    _do_shadow_build(app, docs, "kb-swap", s_settings, s_embedder,
                     target_versions={"embedding_model_version": "v2"})

    result = app.swap_generation("kb-swap", s_settings)

    assert result["previous_active"] == 1
    assert result["new_active"] == 2

    meta = read_meta(Path(s_settings.storage.data_dir) / "kb-swap")
    assert meta.active_generation == 2
    assert meta.shadow_generation is None
    g2 = meta.get_active()
    assert g2 is not None
    assert g2.swap_at  # set
    assert app.get_shadow_kb("kb-swap") is None


def test_swap_promotes_shadow_state_into_active_kb_slot(tmp_path, s_settings, s_embedder):
    docs = _docs(tmp_path)
    _seed_index(s_settings, "kb-swap2")

    app = AppState()
    _do_shadow_build(app, docs, "kb-swap2", s_settings, s_embedder)
    shadow_state = app.get_shadow_kb("kb-swap2")
    assert shadow_state is not None

    app.swap_generation("kb-swap2", s_settings)

    active = app.get_kb("kb-swap2")
    assert active is shadow_state


def test_swap_no_shadow_raises(tmp_path, s_settings):
    _seed_index(s_settings, "kb-noshadow")
    app = AppState()
    with pytest.raises(ServiceError) as exc_info:
        app.swap_generation("kb-noshadow", s_settings)
    assert exc_info.value.code == ErrorCode.INDEXGEN_NO_SHADOW


def test_swap_shadow_still_building_raises(tmp_path, s_settings):
    """Even if shadow exists, status=building means it's not ready."""
    from tagmemorag.indexgen import ShadowGeneration

    kb_root = Path(s_settings.storage.data_dir) / "kb-building"
    kb_root.mkdir(parents=True)
    g1 = ReadyGeneration(
        created_at="2026-05-17T10:00:00Z",
        swap_at="2026-05-17T10:00:00Z",
        retired_at=None,
        parser_version="default", chunker_version="legacy",
        embedding_model_id="x", embedding_model_version="v1",
        index_schema_version=1, chunk_count=0, build_id="b",
    )
    g2_building = ShadowGeneration(
        status=GenerationStatus.BUILDING,
        progress=0.3,
        build_started_at="2026-05-17T11:00:00Z",
        trigger_diff=("embedding_model_version",),
    )
    meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name="kb-building",
        active_generation=1,
        shadow_generation=2,
        generations={1: g1, 2: g2_building},
    )
    write_meta(kb_root, meta)

    app = AppState()
    with pytest.raises(ServiceError) as exc_info:
        app.swap_generation("kb-building", s_settings)
    assert exc_info.value.code == ErrorCode.INDEXGEN_NO_READY_SHADOW


def test_swap_no_index_raises(tmp_path, s_settings):
    app = AppState()
    with pytest.raises(ServiceError) as exc_info:
        app.swap_generation("kb-missing", s_settings)
    assert exc_info.value.code == ErrorCode.INDEXGEN_NO_SUCH_KB


# ============== retire_generation ==============

def _swapped_kb(app: AppState, tmp_path: Path, cfg: Settings, embedder, kb_name: str) -> None:
    docs = _docs(tmp_path)
    _seed_index(cfg, kb_name)
    _do_shadow_build(app, docs, kb_name, cfg, embedder)
    app.swap_generation(kb_name, cfg)


def test_retire_active_raises(tmp_path, s_settings, s_embedder):
    app = AppState()
    _swapped_kb(app, tmp_path, s_settings, s_embedder, "kb-r1")
    with pytest.raises(ServiceError) as exc_info:
        app.retire_generation("kb-r1", 2, s_settings, force=True)
    assert exc_info.value.code == ErrorCode.INDEXGEN_RETIRE_ACTIVE


def test_retire_too_early_without_force(tmp_path, s_settings, s_embedder):
    app = AppState()
    _swapped_kb(app, tmp_path, s_settings, s_embedder, "kb-r2")
    with pytest.raises(ServiceError) as exc_info:
        app.retire_generation("kb-r2", 1, s_settings)
    assert exc_info.value.code == ErrorCode.INDEXGEN_RETIRE_TOO_EARLY
    assert "retry_after_seconds" in exc_info.value.detail


def test_retire_force_bypasses_window(tmp_path, s_settings, s_embedder):
    app = AppState()
    _swapped_kb(app, tmp_path, s_settings, s_embedder, "kb-r3")
    result = app.retire_generation("kb-r3", 1, s_settings, force=True)
    assert result["retired_generation"] == 1
    assert result["force"] is True

    meta = read_meta(Path(s_settings.storage.data_dir) / "kb-r3")
    assert meta.generations[1].retired_at is not None


def test_retire_after_window_succeeds(tmp_path, s_settings, s_embedder):
    """Manually backdate g1.swap_at to simulate >24h elapsed."""
    app = AppState()
    _swapped_kb(app, tmp_path, s_settings, s_embedder, "kb-r4")

    # Backdate g1's swap_at by 25 hours
    kb_root = Path(s_settings.storage.data_dir) / "kb-r4"
    meta = read_meta(kb_root)
    g1 = meta.generations[1]
    backdated = ReadyGeneration(
        created_at=g1.created_at,
        swap_at=(datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        retired_at=g1.retired_at,
        parser_version=g1.parser_version,
        chunker_version=g1.chunker_version,
        embedding_model_id=g1.embedding_model_id,
        embedding_model_version=g1.embedding_model_version,
        index_schema_version=g1.index_schema_version,
        chunk_count=g1.chunk_count,
        build_id=g1.build_id,
    )
    new_gens = dict(meta.generations)
    new_gens[1] = backdated
    write_meta(kb_root, KbMeta(
        schema_version=meta.schema_version,
        kb_name=meta.kb_name,
        active_generation=meta.active_generation,
        shadow_generation=meta.shadow_generation,
        generations=new_gens,
    ))

    result = app.retire_generation("kb-r4", 1, s_settings)
    assert result["retired_generation"] == 1


def test_retire_deletes_generation_directory(tmp_path, s_settings, s_embedder):
    app = AppState()
    _swapped_kb(app, tmp_path, s_settings, s_embedder, "kb-r5")
    g1_dir = Path(s_settings.storage.data_dir) / "kb-r5" / "g1"
    # Note: g1/ may not exist on disk in this test (we seeded the index manually,
    # not via real migration). Create a sentinel file to verify retire deletes.
    g1_dir.mkdir(parents=True, exist_ok=True)
    (g1_dir / "sentinel.txt").write_text("data", encoding="utf-8")

    app.retire_generation("kb-r5", 1, s_settings, force=True)
    assert not g1_dir.exists()


def test_retire_no_such_generation_raises(tmp_path, s_settings, s_embedder):
    app = AppState()
    _swapped_kb(app, tmp_path, s_settings, s_embedder, "kb-r6")
    with pytest.raises(ServiceError) as exc_info:
        app.retire_generation("kb-r6", 99, s_settings, force=True)
    assert exc_info.value.code == ErrorCode.INDEXGEN_NO_SUCH_GENERATION


def test_retire_shadow_raises(tmp_path, s_settings, s_embedder):
    docs = _docs(tmp_path)
    _seed_index(s_settings, "kb-r7")
    app = AppState()
    _do_shadow_build(app, docs, "kb-r7", s_settings, s_embedder)
    # shadow_generation=2 now exists
    with pytest.raises(ServiceError) as exc_info:
        app.retire_generation("kb-r7", 2, s_settings, force=True)
    assert exc_info.value.code == ErrorCode.INDEXGEN_RETIRE_SHADOW
