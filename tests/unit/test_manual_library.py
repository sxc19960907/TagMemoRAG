from __future__ import annotations

import json
from pathlib import Path
import time

import pytest

from tagmemorag.config import ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.errors import ServiceError
from tagmemorag.manual_library import (
    delete_manual,
    disable_manual,
    library_root,
    list_records,
    load_manifest,
    mark_pending,
    safe_source_path,
    update_manual_metadata,
    upsert_manual,
    validate_metadata,
)
from tagmemorag.state import AppState, build_kb, start_library_rebuild


@pytest.fixture
def library_config(tmp_path) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        model={"dim": 64},
    )


def _metadata(source_file: str = "coffee/cm1.md", manual_id: str = "cm1") -> dict[str, object]:
    return {
        "manual_id": manual_id,
        "title": "CM1 Manual",
        "source_file": source_file,
        "product_category": "coffee",
        "language": "zh-CN",
        "tags": ["Maintenance Task"],
    }


def test_safe_source_path_rejects_traversal_and_unsupported_suffix(library_config):
    with pytest.raises(ServiceError) as traversal:
        safe_source_path("default", "../escape.md", library_config)
    assert traversal.value.code == "INVALID_INPUT"

    with pytest.raises(ServiceError) as suffix:
        safe_source_path("default", "coffee/manual.exe", library_config)
    assert suffix.value.code == "INVALID_INPUT"


def test_validate_metadata_normalizes_and_reports_duplicate_manual_id(library_config):
    record = upsert_manual("default", _metadata(), b"# Use\nClean weekly.\n", library_config)
    assert record.metadata.tags == ("maintenance-task",)

    result = validate_metadata("default", _metadata("coffee/other.md"), library_config, mode="create")

    assert not result.valid
    assert result.messages[0].code == "DUPLICATE_MANUAL_ID"


def test_upsert_update_disable_delete_and_manifest_pending(library_config):
    record = upsert_manual("default", _metadata(), b"# Use\nClean weekly.\n", library_config)
    root = library_root("default", library_config)
    assert (root / "coffee" / "cm1.md").exists()
    assert (root / "coffee" / "cm1.metadata.json").exists()
    manifest = load_manifest("default", library_config)
    assert manifest.pending_changes
    assert manifest.dirty_manuals["cm1"].operation == "upsert"

    updated = update_manual_metadata("default", "cm1", {"product_model": "CM1", "tags": ["Steam Wand"]}, library_config)
    assert updated.metadata.product_model == "CM1"
    assert updated.metadata.tags == ("steam-wand",)
    assert load_manifest("default", library_config).dirty_manuals["cm1"].operation == "metadata_update"

    disabled = disable_manual("default", "cm1", library_config)
    assert disabled.status == "disabled"
    assert load_manifest("default", library_config).dirty_manuals["cm1"].operation == "disable"
    sidecar = json.loads((root / "coffee" / "cm1.metadata.json").read_text(encoding="utf-8"))
    assert sidecar["status"] == "disabled"

    result = delete_manual("default", "cm1", library_config)
    assert result["status"] == "deleted"
    assert load_manifest("default", library_config).dirty_manuals["cm1"].operation == "hard_delete"
    assert not (root / "coffee" / "cm1.md").exists()
    assert not list_records("default", library_config)


def test_disabled_manual_is_skipped_by_build_kb(library_config, fake_embedder):
    upsert_manual("default", _metadata("coffee/active.md", "active"), b"# Active\nSteam works.\n", library_config)
    upsert_manual("default", _metadata("coffee/disabled.md", "disabled"), b"# Disabled\nHidden.\n", library_config)
    disable_manual("default", "disabled", library_config)

    state = build_kb(library_root("default", library_config), "default", library_config, embedder=fake_embedder)

    manual_ids = {node["metadata"]["manual_id"] for _, node in state.graph.nodes(data=True)}
    assert manual_ids == {"active"}


def test_failed_library_rebuild_keeps_old_graph_and_pending_marker(library_config, fake_embedder):
    upsert_manual("default", _metadata("coffee/active.md", "active"), b"# Active\nSteam works.\n", library_config)
    old_state = build_kb(library_root("default", library_config), "default", library_config, embedder=fake_embedder)
    mark_pending("default", library_config, pending=False, build_id=old_state.build_id)
    app = AppState(old_state)

    upsert_manual("default", _metadata("coffee/bad.md", "bad"), b"# Bad\nHidden.\n", library_config)
    (library_root("default", library_config) / "coffee" / "bad.metadata.json").write_text("{bad-json", encoding="utf-8")

    task = start_library_rebuild(app, "default", library_config, embedder=fake_embedder)
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "failed"
    assert app.get_current("default").build_id == old_state.build_id
    assert load_manifest("default", library_config).pending_changes is True


def test_incremental_library_rebuild_reuses_unchanged_chunks(library_config, fake_embedder):
    upsert_manual("default", _metadata("coffee/a.md", "a"), b"# A\nSteam works.\n", library_config)
    upsert_manual("default", _metadata("coffee/b.md", "b"), b"# B\nClean weekly.\n", library_config)
    old_state = build_kb(library_root("default", library_config), "default", library_config, embedder=fake_embedder)
    mark_pending("default", library_config, pending=False, build_id=old_state.build_id)
    app = AppState(old_state)

    update_manual_metadata("default", "a", {"product_model": "A1"}, library_config)
    task = start_library_rebuild(app, "default", library_config, embedder=fake_embedder, mode="incremental")
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "done"
    assert task.effective_mode == "incremental"
    assert task.dirty_manual_count == 1
    assert task.reused_chunk_count == 1
    assert task.embedded_chunk_count == 1
    assert load_manifest("default", library_config).dirty_manuals == {}
    assert app.get_current("default").meta["rebuild_mode"] == "incremental"
    data_dir = Path(library_config.storage.data_dir)
    assert json.loads((data_dir / "default" / "chunk_identity.json").read_text(encoding="utf-8"))["chunks"]
    assert json.loads((data_dir / "default" / "rebuild_impact.json").read_text(encoding="utf-8"))["summary"]["chunks_reused"] >= 1


def test_incremental_rebuild_reuses_unchanged_dirty_manual_chunk(library_config, fake_embedder):
    upsert_manual("default", _metadata("coffee/a.md", "a"), b"# Same\nSteam works.\n# Changed\nOld text.\n", library_config)
    old_state = build_kb(library_root("default", library_config), "default", library_config, embedder=fake_embedder)
    app = AppState(old_state)
    mark_pending("default", library_config, pending=True, build_id=old_state.build_id)
    first = start_library_rebuild(app, "default", library_config, embedder=fake_embedder)
    for _ in range(100):
        if first.status != "running":
            break
        time.sleep(0.01)
    assert first.status == "done"

    (library_root("default", library_config) / "coffee" / "a.md").write_text("# Same\nSteam works.\n# Changed\nNew text.\n", encoding="utf-8")
    update_manual_metadata("default", "a", {"product_model": "A1"}, library_config)
    task = start_library_rebuild(app, "default", library_config, embedder=fake_embedder, mode="incremental")
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "done"
    assert task.effective_mode == "incremental"
    assert task.reused_chunk_count == 1
    assert task.embedded_chunk_count == 1
    assert task.chunk_identity_fallback_reason == ""
    assert task.impact_report["summary"]["chunks_reused"] >= 1


def test_auto_mode_threshold_chooses_full(library_config, fake_embedder):
    cfg = library_config.model_copy(
        update={"manual_library": ManualLibraryConfig(root_dir=library_config.manual_library.root_dir, incremental_auto_max_dirty_manuals=0)}
    )
    upsert_manual("default", _metadata("coffee/a.md", "a"), b"# A\nSteam works.\n", cfg)
    old_state = build_kb(library_root("default", cfg), "default", cfg, embedder=fake_embedder)
    mark_pending("default", cfg, pending=False, build_id=old_state.build_id)
    app = AppState(old_state)

    update_manual_metadata("default", "a", {"product_model": "A1"}, cfg)
    task = start_library_rebuild(app, "default", cfg, embedder=fake_embedder, mode="auto")
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "done"
    assert task.effective_mode == "full"
    assert task.auto_decision_reason == "auto_dirty_manual_threshold_exceeded"
    assert app.get_current("default").meta["auto_decision_reason"] == "auto_dirty_manual_threshold_exceeded"


def test_incremental_rebuild_falls_back_without_dirty_state(library_config, fake_embedder):
    upsert_manual("default", _metadata("coffee/a.md", "a"), b"# A\nSteam works.\n", library_config)
    old_state = build_kb(library_root("default", library_config), "default", library_config, embedder=fake_embedder)
    mark_pending("default", library_config, pending=False, build_id=old_state.build_id)
    mark_pending("default", library_config, pending=True)
    app = AppState(old_state)

    task = start_library_rebuild(app, "default", library_config, embedder=fake_embedder, mode="incremental")
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "done"
    assert task.effective_mode == "full"
    assert task.fallback_reason == "missing_dirty_state"
