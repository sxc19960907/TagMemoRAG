"""Tests for AppState dual-generation slot (T1 Slice 4)."""

from __future__ import annotations

import threading

import pytest

from tagmemorag.indexgen import (
    INDEXGEN_META_SCHEMA_VERSION,
    GenerationStatus,
    KbMeta,
    ReadyGeneration,
    ShadowGeneration,
)
from tagmemorag.state import AppState, build_kb, save_kb


def _ready() -> ReadyGeneration:
    return ReadyGeneration(
        created_at="2026-05-17T10:00:00Z",
        swap_at="2026-05-17T10:00:00Z",
        retired_at=None,
        parser_version="v3",
        chunker_version="v2",
        embedding_model_id="bge-m3",
        embedding_model_version="v1",
        index_schema_version=4,
        chunk_count=10,
        build_id="20260517100000",
    )


def _shadow() -> ShadowGeneration:
    return ShadowGeneration(
        status=GenerationStatus.BUILDING,
        progress=0.5,
        build_started_at="2026-05-17T11:00:00Z",
        trigger_diff=("embedding_model_version",),
    )


def _kb_meta(kb_name: str, *, with_shadow: bool = False) -> KbMeta:
    gens: dict[int, ReadyGeneration | ShadowGeneration] = {1: _ready()}
    shadow_id = None
    if with_shadow:
        gens[2] = _shadow()
        shadow_id = 2
    return KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name=kb_name,
        active_generation=1,
        shadow_generation=shadow_id,
        generations=gens,
    )


def test_appstate_initial_dual_slots_are_empty():
    app = AppState()
    assert app.shadow_kbs == {}
    assert app.generation_meta == {}
    assert app.get_shadow_kb("default") is None
    assert app.get_generation_meta("default") is None


def test_install_and_clear_shadow(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# Title\nhello\n", encoding="utf-8")
    state = build_kb(docs, "kb-a", test_config, embedder=fake_embedder)
    save_kb(state, test_config)

    app = AppState()
    app.install_shadow("kb-a", state)
    assert app.get_shadow_kb("kb-a") is state

    cleared = app.clear_shadow("kb-a")
    assert cleared is state
    assert app.get_shadow_kb("kb-a") is None


def test_shadow_does_not_appear_via_get_kb(tmp_path, test_config, fake_embedder):
    """Read paths use get_kb; shadow must never leak there."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# Title\nhello\n", encoding="utf-8")
    state = build_kb(docs, "kb-a", test_config, embedder=fake_embedder)
    save_kb(state, test_config)

    app = AppState()
    app.install_shadow("kb-a", state)

    from tagmemorag.errors import KbNotLoadedError
    with pytest.raises(KbNotLoadedError):
        app.get_kb("kb-a")  # active slot is empty; shadow slot must not satisfy


def test_generation_meta_round_trip():
    app = AppState()
    meta = _kb_meta("default")
    app.set_generation_meta("default", meta)
    assert app.get_generation_meta("default") == meta


def test_generation_meta_update_overwrites():
    app = AppState()
    app.set_generation_meta("default", _kb_meta("default"))
    updated = _kb_meta("default", with_shadow=True)
    app.set_generation_meta("default", updated)
    fetched = app.get_generation_meta("default")
    assert fetched is not None
    assert fetched.shadow_generation == 2


def test_per_kb_isolation_in_shadow_and_meta(tmp_path, test_config, fake_embedder):
    docs_a = tmp_path / "a"
    docs_b = tmp_path / "b"
    docs_a.mkdir()
    docs_b.mkdir()
    (docs_a / "m.md").write_text("# A\nx\n", encoding="utf-8")
    (docs_b / "m.md").write_text("# B\ny\n", encoding="utf-8")
    state_a = build_kb(docs_a, "kb-a", test_config, embedder=fake_embedder)
    state_b = build_kb(docs_b, "kb-b", test_config, embedder=fake_embedder)
    save_kb(state_a, test_config)
    save_kb(state_b, test_config)

    app = AppState()
    app.install_shadow("kb-a", state_a)
    app.set_generation_meta("kb-a", _kb_meta("kb-a"))
    # kb-b has neither shadow nor meta
    assert app.get_shadow_kb("kb-a") is state_a
    assert app.get_shadow_kb("kb-b") is None
    assert app.get_generation_meta("kb-a") is not None
    assert app.get_generation_meta("kb-b") is None


def test_shadow_and_meta_thread_safety_smoke(tmp_path, test_config, fake_embedder):
    """Smoke: concurrent installs from threads do not corrupt state."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "m.md").write_text("# T\nv\n", encoding="utf-8")
    state = build_kb(docs, "kb-c", test_config, embedder=fake_embedder)
    save_kb(state, test_config)

    app = AppState()

    def worker(kb: str):
        app.install_shadow(kb, state)
        app.set_generation_meta(kb, _kb_meta(kb))

    threads = [threading.Thread(target=worker, args=(f"kb-{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(app.shadow_kbs) == 8
    assert len(app.generation_meta) == 8
    for i in range(8):
        assert app.get_shadow_kb(f"kb-{i}") is state


def _legacy_kb_layout(tmp_path, kb_name: str) -> None:
    import json
    kb_root = tmp_path / kb_name
    kb_root.mkdir(parents=True)
    (kb_root / "graph.json").write_text(
        json.dumps({"nodes": [{"id": 1}, {"id": 2}], "meta": {"build_id": "20260517000000"}}),
        encoding="utf-8",
    )
    (kb_root / "vectors.npz").write_bytes(b"\x00" * 8)
    (kb_root / "anchors.json").write_text("[]", encoding="utf-8")


def test_migrate_kb_for_indexgen_runs_lazy_migration_and_caches_meta(
    tmp_path, test_config
):
    test_config.storage.data_dir = str(tmp_path)
    test_config.vector_store.provider = "npz"
    _legacy_kb_layout(tmp_path, "kb-mig")

    app = AppState()
    result = app.migrate_kb_for_indexgen("kb-mig", test_config)

    assert result["status"] == "migrated"
    assert (tmp_path / "kb-mig" / "g1" / "graph.json").exists()
    cached = app.get_generation_meta("kb-mig")
    assert cached is not None
    assert cached.active_generation == 1


def test_migrate_kb_for_indexgen_is_idempotent(tmp_path, test_config):
    test_config.storage.data_dir = str(tmp_path)
    test_config.vector_store.provider = "npz"
    _legacy_kb_layout(tmp_path, "kb-mig")

    app = AppState()
    first = app.migrate_kb_for_indexgen("kb-mig", test_config)
    second = app.migrate_kb_for_indexgen("kb-mig", test_config)
    assert first["status"] == "migrated"
    assert second["status"] == "already_migrated"


def test_migrate_kb_for_indexgen_marks_orphan_shadow_failed(tmp_path, test_config):
    """If index.json has shadow.status=building but no in-memory shadow exists,
    mark the meta entry status=failed."""
    import json
    test_config.storage.data_dir = str(tmp_path)
    test_config.vector_store.provider = "npz"
    kb_root = tmp_path / "kb-orphan"
    (kb_root / "g1").mkdir(parents=True)
    (kb_root / "g1" / "graph.json").write_text("{}", encoding="utf-8")
    meta_payload = {
        "schema_version": INDEXGEN_META_SCHEMA_VERSION,
        "kb_name": "kb-orphan",
        "active_generation": 1,
        "shadow_generation": 2,
        "generations": {
            "1": _ready().to_dict(),
            "2": _shadow().to_dict(),
        },
    }
    (kb_root / "index.json").write_text(json.dumps(meta_payload), encoding="utf-8")

    app = AppState()
    result = app.migrate_kb_for_indexgen("kb-orphan", test_config)

    assert result["status"] == "already_migrated"
    assert result["orphan_shadow_detected"] is True
    cached = app.get_generation_meta("kb-orphan")
    assert cached is not None
    shadow = cached.get_shadow()
    assert shadow is not None
    assert shadow.status == GenerationStatus.FAILED
    assert shadow.error == {"type": "OrphanedShadow", "message": "process restarted during shadow build"}


def test_migrate_kb_for_indexgen_keeps_running_shadow_when_in_memory_present(
    tmp_path, test_config, fake_embedder
):
    """If meta says shadow=building AND in-memory shadow exists (e.g. brought in
    by previous test setup), do not mark failed."""
    import json
    test_config.storage.data_dir = str(tmp_path)
    test_config.vector_store.provider = "npz"
    kb_root = tmp_path / "kb-living"
    (kb_root / "g1").mkdir(parents=True)
    (kb_root / "g1" / "graph.json").write_text("{}", encoding="utf-8")
    meta_payload = {
        "schema_version": INDEXGEN_META_SCHEMA_VERSION,
        "kb_name": "kb-living",
        "active_generation": 1,
        "shadow_generation": 2,
        "generations": {
            "1": _ready().to_dict(),
            "2": _shadow().to_dict(),
        },
    }
    (kb_root / "index.json").write_text(json.dumps(meta_payload), encoding="utf-8")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "m.md").write_text("# T\nv\n", encoding="utf-8")
    state = build_kb(docs, "kb-living", test_config, embedder=fake_embedder)
    save_kb(state, test_config)

    app = AppState()
    app.install_shadow("kb-living", state)
    result = app.migrate_kb_for_indexgen("kb-living", test_config)

    assert result["orphan_shadow_detected"] is False
    cached = app.get_generation_meta("kb-living")
    assert cached is not None
    shadow = cached.get_shadow()
    assert shadow is not None
    assert shadow.status == GenerationStatus.BUILDING
