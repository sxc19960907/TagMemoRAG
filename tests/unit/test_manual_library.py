from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import time

import numpy as np
import pytest

from tagmemorag.config import ManualLibraryConfig, ParserConfig, SearchConfig, Settings, StorageConfig, VectorStoreConfig
from tagmemorag.errors import ServiceError
from tagmemorag.manual_library import (
    build_dirty_state_report,
    delete_manual,
    disable_manual,
    library_root,
    list_records,
    load_manifest,
    mark_pending,
    materialize_registry_build_source,
    migrate_sidecars_to_registry,
    registry_inspect,
    safe_source_path,
    update_manual_metadata,
    upsert_manual,
    verify_registry_blobs,
    validate_metadata,
)
from tagmemorag.manual_registry import create_registry
from tagmemorag.tag_store import upsert_manual_tags
from tagmemorag.search_runtime import execute_search
from tagmemorag.state import AppState, build_kb, start_library_rebuild
from tests.unit.test_storage_state import FakeQdrantClient


class KeywordEmbedder:
    model_name = "keyword-embedder"
    dim = 4

    def encode_batch(self, texts):
        return np.asarray([self._encode_one(text) for text in texts], dtype=np.float32)

    def encode_query(self, text):
        return self._encode_one(text)

    def _encode_one(self, text):
        lowered = text.lower()
        vec = np.zeros(self.dim, dtype=np.float32)
        if "alpha" in lowered:
            vec[0] = 1.0
        if "bravo" in lowered:
            vec[1] = 1.0
        if "charlie" in lowered:
            vec[2] = 1.0
        if "delta" in lowered:
            vec[3] = 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec


class FakeS3ClientError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeS3Client:
    def __init__(self):
        self.objects = {}
        self.fail_put = False

    def put_object(self, **kwargs):
        if self.fail_put:
            raise FakeS3ClientError("AccessDenied")
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = {
            "Body": kwargs["Body"],
            "ContentType": kwargs.get("ContentType", ""),
            "Metadata": kwargs.get("Metadata", {}),
        }
        return {}

    def get_object(self, **kwargs):
        try:
            obj = self.objects[(kwargs["Bucket"], kwargs["Key"])]
        except KeyError as exc:
            raise FakeS3ClientError("NoSuchKey") from exc
        return {"Body": BytesIO(obj["Body"])}

    def head_object(self, **kwargs):
        if (kwargs["Bucket"], kwargs["Key"]) not in self.objects:
            raise FakeS3ClientError("404")
        return {}

    def delete_object(self, **kwargs):
        self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)
        return {}


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


def _persist_qdrant_baseline(state, cfg) -> None:
    from tagmemorag.chunk_identity import build_chunk_identity_map, identity_path, save_chunk_identity
    from tagmemorag.state import save_kb

    save_kb(state, cfg)
    save_chunk_identity(identity_path(state.kb_name, cfg), build_chunk_identity_map(state.graph, kb_name=state.kb_name, build_id=state.build_id, cfg=cfg))
    mark_pending(state.kb_name, cfg, pending=False, build_id=state.build_id)


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


def test_validate_metadata_emits_non_blocking_tag_ordering_hint(library_config):
    payload = _metadata("coffee/multi-tag.md", manual_id="cm-multi")
    payload["tags"] = ["fault-code", "diagnostics", "washer"]

    result = validate_metadata("default", payload, library_config, mode="create")

    assert result.valid is True
    hints = [m for m in result.messages if m.code == "TAG_ORDERING_HINT"]
    assert len(hints) == 1
    assert hints[0].detail.get("severity") == "info"
    assert hints[0].field == "tags"


def test_validate_metadata_skips_ordering_hint_for_single_tag(library_config):
    result = validate_metadata("default", _metadata("coffee/single.md", manual_id="cm-solo"), library_config, mode="create")

    assert result.valid is True
    assert all(m.code != "TAG_ORDERING_HINT" for m in result.messages)


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


def test_delete_manual_cleans_phase0_tag_links_and_marks_epa_dirty(library_config):
    upsert_manual("default", _metadata(), b"# Use\nClean weekly.\n", library_config)
    with create_registry(Path(library_config.storage.data_dir) / "manual_registry.sqlite3").connection() as conn:
        upsert_manual_tags(conn, "default", "cm1", ["maintenance-task"])

    result = delete_manual("default", "cm1", library_config)

    with create_registry(Path(library_config.storage.data_dir) / "manual_registry.sqlite3").connection() as conn:
        manual_tag_count = conn.execute("SELECT count(*) AS count FROM manual_tags").fetchone()["count"]
        tag_count = conn.execute("SELECT count(*) AS count FROM tags").fetchone()["count"]

    assert result["orphan_tags_removed"] == 1
    assert manual_tag_count == 0
    assert tag_count == 0
    assert (Path(library_config.storage.data_dir) / "_global" / "epa_basis.dirty").exists()


def test_registry_delete_manual_cleans_phase0_tag_links(tmp_path):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(
            root_dir=str(tmp_path / "manuals"),
            registry_backend="sqlite",
            registry_path=str(tmp_path / "registry.sqlite3"),
            blob_backend="local",
            blob_root_dir=str(tmp_path / "blobs"),
        ),
        model={"dim": 64},
    )
    upsert_manual("default", _metadata(), b"# Use\nClean weekly.\n", cfg)
    with create_registry(cfg.manual_library.registry_path).connection() as conn:
        upsert_manual_tags(conn, "default", "cm1", ["maintenance-task"])

    result = delete_manual("default", "cm1", cfg)

    with create_registry(cfg.manual_library.registry_path).connection() as conn:
        manual_tag_count = conn.execute("SELECT count(*) AS count FROM manual_tags").fetchone()["count"]
        tag_count = conn.execute("SELECT count(*) AS count FROM tags").fetchone()["count"]

    assert result["orphan_tags_removed"] == 1
    assert result["registry_backend"] == "sqlite"
    assert manual_tag_count == 0
    assert tag_count == 0


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


def test_incremental_rebuild_falls_back_when_parser_profile_changes(library_config, fake_embedder):
    upsert_manual("default", _metadata("coffee/a.md", "a"), b"# Same\nSteam works.\n", library_config)
    old_state = build_kb(library_root("default", library_config), "default", library_config, embedder=fake_embedder)
    app = AppState(old_state)
    mark_pending("default", library_config, pending=True, build_id=old_state.build_id)
    first = start_library_rebuild(app, "default", library_config, embedder=fake_embedder)
    for _ in range(100):
        if first.status != "running":
            break
        time.sleep(0.01)
    assert first.status == "done"

    cfg = library_config.model_copy(update={"parser": ParserConfig(pdf_profile="generic")})
    update_manual_metadata("default", "a", {"product_model": "A1"}, cfg)
    task = start_library_rebuild(app, "default", cfg, embedder=fake_embedder, mode="incremental")
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "done"
    assert task.effective_mode == "full"
    assert task.fallback_reason == "parser_config_changed"
    assert task.chunk_identity_fallback_reason == "parser_config_changed"


def test_incremental_rebuild_falls_back_when_overlap_config_changes(library_config, fake_embedder):
    upsert_manual(
        "default",
        _metadata("coffee/a.md", "a"),
        b"# Same\nOpen the service panel. Rinse the filter. Close the panel.\n",
        library_config,
    )
    old_state = build_kb(library_root("default", library_config), "default", library_config, embedder=fake_embedder)
    app = AppState(old_state)
    mark_pending("default", library_config, pending=True, build_id=old_state.build_id)
    first = start_library_rebuild(app, "default", library_config, embedder=fake_embedder)
    for _ in range(100):
        if first.status != "running":
            break
        time.sleep(0.01)
    assert first.status == "done"

    cfg = library_config.model_copy(update={"parser": ParserConfig(overlap_chars=16)})
    update_manual_metadata("default", "a", {"product_model": "A1"}, cfg)
    task = start_library_rebuild(app, "default", cfg, embedder=fake_embedder, mode="incremental")
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "done"
    assert task.effective_mode == "full"
    assert task.fallback_reason == "parser_config_changed"
    assert task.chunk_identity_fallback_reason == "parser_config_changed"


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


def test_registry_mode_upload_list_migrate_and_rebuild(tmp_path, fake_embedder):
    legacy_cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "legacy-data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        model={"dim": 64},
    )
    upsert_manual("default", _metadata("coffee/legacy.md", "legacy"), b"# Legacy\nSteam works.\n", legacy_cfg)

    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(
            root_dir=str(tmp_path / "manuals"),
            registry_backend="sqlite",
            registry_path=str(tmp_path / "registry.sqlite3"),
            blob_backend="local",
            blob_root_dir=str(tmp_path / "blobs"),
        ),
        model={"dim": 64},
    )
    dry_run = migrate_sidecars_to_registry("default", cfg, dry_run=True)
    assert dry_run.imported_records == 1
    committed = migrate_sidecars_to_registry("default", cfg, dry_run=False)
    assert committed.imported_records == 1
    second = migrate_sidecars_to_registry("default", cfg, dry_run=False)
    assert second.skipped_records == 1

    uploaded = upsert_manual("default", _metadata("coffee/new.md", "new"), b"# New\nClean weekly.\n", cfg)
    assert uploaded.registry_backend == "sqlite"
    assert uploaded.storage_backend == "local"
    assert uploaded.blob_key
    assert uploaded.size_bytes > 0
    assert registry_inspect("default", cfg)["record_count"] == 2
    assert verify_registry_blobs("default", cfg)["missing_count"] == 0

    state = build_kb(library_root("default", legacy_cfg), "default", legacy_cfg, embedder=fake_embedder)
    app = AppState(state)
    task = start_library_rebuild(app, "default", cfg, embedder=fake_embedder)
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "done"
    manual_ids = {node["metadata"]["manual_id"] for _, node in app.get_current("default").graph.nodes(data=True)}
    assert manual_ids == {"legacy", "new"}
    assert load_manifest("default", cfg).pending_changes is False


def test_registry_s3_upload_migrate_verify_and_rebuild(monkeypatch, tmp_path, fake_embedder):
    from tagmemorag.manual_blob_store import S3ManualBlobStore

    legacy_cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "legacy-data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        model={"dim": 64},
    )
    upsert_manual("default", _metadata("coffee/legacy.md", "legacy"), b"# Legacy\nalpha steam.\n", legacy_cfg)

    client = FakeS3Client()
    monkeypatch.setattr(
        "tagmemorag.manual_blob_store.create_blob_store",
        lambda cfg: S3ManualBlobStore(cfg.manual_library.s3_bucket, cfg.manual_library.s3_prefix, client=client),
    )
    monkeypatch.setattr(
        "tagmemorag.manual_library.create_blob_store",
        lambda cfg: S3ManualBlobStore(cfg.manual_library.s3_bucket, cfg.manual_library.s3_prefix, client=client),
    )
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(
            root_dir=str(tmp_path / "manuals"),
            registry_backend="sqlite",
            registry_path=str(tmp_path / "registry.sqlite3"),
            blob_backend="s3",
            s3_bucket="manuals",
            s3_prefix="/prod//",
        ),
        model={"dim": 64},
    )

    dry_run = migrate_sidecars_to_registry("default", cfg, dry_run=True)
    assert dry_run.imported_records == 1
    assert client.objects == {}
    committed = migrate_sidecars_to_registry("default", cfg, dry_run=False)
    assert committed.imported_records == 1
    uploaded = upsert_manual("default", _metadata("coffee/new.md", "new"), b"# New\nbravo clean.\n", cfg)

    assert uploaded.storage_backend == "s3"
    assert uploaded.blob_key.startswith("prod/default/new/1/")
    assert verify_registry_blobs("default", cfg)["missing_count"] == 0
    assert len(client.objects) == 2

    state = build_kb(library_root("default", legacy_cfg), "default", legacy_cfg, embedder=fake_embedder)
    app = AppState(state)
    task = start_library_rebuild(app, "default", cfg, embedder=fake_embedder)
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "done"
    manual_ids = {node["metadata"]["manual_id"] for _, node in app.get_current("default").graph.nodes(data=True)}
    assert manual_ids == {"legacy", "new"}
    assert load_manifest("default", cfg).pending_changes is False


def test_s3_upload_failure_does_not_commit_registry_or_dirty(monkeypatch, tmp_path):
    from tagmemorag.manual_blob_store import S3ManualBlobStore
    from tagmemorag.manual_registry import create_registry

    client = FakeS3Client()
    client.fail_put = True
    monkeypatch.setattr(
        "tagmemorag.manual_library.create_blob_store",
        lambda cfg: S3ManualBlobStore(cfg.manual_library.s3_bucket, cfg.manual_library.s3_prefix, client=client),
    )
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(
            root_dir=str(tmp_path / "manuals"),
            registry_backend="sqlite",
            registry_path=str(tmp_path / "registry.sqlite3"),
            blob_backend="s3",
            s3_bucket="manuals",
        ),
        model={"dim": 64},
    )

    with pytest.raises(ServiceError) as exc:
        upsert_manual("default", _metadata("coffee/new.md", "new"), b"# New\nbravo clean.\n", cfg)

    assert exc.value.code == "STORAGE_LOAD_FAILED"
    assert create_registry(cfg.manual_library.registry_path).list("default") == []
    assert load_manifest("default", cfg).pending_changes is False


def test_s3_missing_object_rebuild_preserves_old_graph_and_dirty(monkeypatch, tmp_path, fake_embedder):
    from tagmemorag.manual_blob_store import S3ManualBlobStore

    client = FakeS3Client()
    monkeypatch.setattr(
        "tagmemorag.manual_library.create_blob_store",
        lambda cfg: S3ManualBlobStore(cfg.manual_library.s3_bucket, cfg.manual_library.s3_prefix, client=client),
    )
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(
            root_dir=str(tmp_path / "manuals"),
            registry_backend="sqlite",
            registry_path=str(tmp_path / "registry.sqlite3"),
            blob_backend="s3",
            s3_bucket="manuals",
        ),
        model={"dim": 64},
    )
    upsert_manual("default", _metadata("coffee/a.md", "a"), b"# A\nSteam works.\n", cfg)
    with materialize_registry_build_source("default", cfg) as docs_dir:
        old_state = build_kb(docs_dir, "default", cfg, embedder=fake_embedder)
    mark_pending("default", cfg, pending=False, build_id=old_state.build_id)
    app = AppState(old_state)

    upsert_manual("default", _metadata("coffee/b.md", "b"), b"# B\nClean weekly.\n", cfg)
    client.objects.clear()
    task = start_library_rebuild(app, "default", cfg, embedder=fake_embedder)
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "failed"
    assert app.get_current("default").build_id == old_state.build_id
    assert load_manifest("default", cfg).pending_changes is True


@pytest.fixture
def qdrant_library_config(monkeypatch, tmp_path) -> Settings:
    FakeQdrantClient.reset()
    monkeypatch.setattr("tagmemorag.storage.qdrant_vector.QdrantVectorStore._create_client", lambda *args, **kwargs: FakeQdrantClient())
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        vector_store=VectorStoreConfig(provider="qdrant", collection_prefix="test"),
        model={"dim": 64},
    )


def test_qdrant_library_rebuild_full_sync_deletes_stale_points(qdrant_library_config, fake_embedder):
    upsert_manual("default", _metadata("coffee/a.md", "a"), b"# A\nSteam works.\n", qdrant_library_config)
    upsert_manual("default", _metadata("coffee/b.md", "b"), b"# B\nClean weekly.\n", qdrant_library_config)
    old_state = build_kb(library_root("default", qdrant_library_config), "default", qdrant_library_config, embedder=fake_embedder)
    _persist_qdrant_baseline(old_state, qdrant_library_config)
    app = AppState(old_state)
    delete_manual("default", "b", qdrant_library_config)

    task = start_library_rebuild(app, "default", qdrant_library_config, embedder=fake_embedder, mode="full")
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "done"
    assert task.qdrant_sync["strategy"] == "full_sync"
    assert task.qdrant_sync["points_deleted"] == 1
    assert FakeQdrantClient.delete_calls[-1] == ("test_default", [1])
    assert sorted(FakeQdrantClient.collections["test_default"]) == [0]
    meta = json.loads((Path(qdrant_library_config.storage.data_dir) / "default" / "meta.json").read_text(encoding="utf-8"))
    assert meta["qdrant_sync"]["points_deleted"] == 1
    impact = json.loads((Path(qdrant_library_config.storage.data_dir) / "default" / "rebuild_impact.json").read_text(encoding="utf-8"))
    assert impact["qdrant_sync"]["strategy"] == "full_sync"


def test_qdrant_incremental_sync_skips_reused_points(qdrant_library_config, fake_embedder):
    upsert_manual("default", _metadata("coffee/a.md", "a"), b"# A\nSteam works.\n", qdrant_library_config)
    upsert_manual("default", _metadata("coffee/b.md", "b"), b"# B\nClean weekly.\n", qdrant_library_config)
    old_state = build_kb(library_root("default", qdrant_library_config), "default", qdrant_library_config, embedder=fake_embedder)
    _persist_qdrant_baseline(old_state, qdrant_library_config)
    app = AppState(old_state)
    FakeQdrantClient.upsert_calls.clear()
    update_manual_metadata("default", "a", {"product_model": "A1"}, qdrant_library_config)

    task = start_library_rebuild(app, "default", qdrant_library_config, embedder=fake_embedder, mode="incremental")
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "done"
    assert task.qdrant_sync == {
        "provider": "qdrant",
        "strategy": "point_incremental",
        "points_upserted": 1,
        "points_deleted": 0,
        "points_reused": 1,
        "fallback_reason": "",
    }
    assert FakeQdrantClient.upsert_calls[-1] == ("test_default", [0])
    assert FakeQdrantClient.set_payload_calls == []
    assert FakeQdrantClient.batch_payload_calls[-1][0] == "test_default"
    assert len(FakeQdrantClient.batch_payload_calls[-1][1]) == 1
    reused_node_id, reused_payload = FakeQdrantClient.batch_payload_calls[-1][1][0]
    assert reused_node_id == 1
    assert reused_payload == {
        "kb_name": "default",
        "node_id": 1,
        "build_id": app.get_current("default").build_id,
        "doc_id": "b",
        "chunk_id": FakeQdrantClient.collections["test_default"][1].payload["chunk_id"],
        "chunk_identity_key": FakeQdrantClient.collections["test_default"][1].payload["chunk_identity_key"],
        "manual_id": "b",
        "source_file": "coffee/b.md",
        "text_hash": FakeQdrantClient.collections["test_default"][1].payload["text_hash"],
    }
    assert FakeQdrantClient.collections["test_default"][0].payload["build_id"] == app.get_current("default").build_id
    assert FakeQdrantClient.collections["test_default"][1].payload["build_id"] == app.get_current("default").build_id


def test_qdrant_incremental_sync_batches_multiple_reused_payloads(qdrant_library_config, fake_embedder):
    upsert_manual("default", _metadata("coffee/a.md", "a"), b"# A\nSteam works.\n", qdrant_library_config)
    upsert_manual("default", _metadata("coffee/b.md", "b"), b"# B\nClean weekly.\n", qdrant_library_config)
    upsert_manual("default", _metadata("coffee/c.md", "c"), b"# C\nDescale monthly.\n", qdrant_library_config)
    old_state = build_kb(library_root("default", qdrant_library_config), "default", qdrant_library_config, embedder=fake_embedder)
    _persist_qdrant_baseline(old_state, qdrant_library_config)
    app = AppState(old_state)
    FakeQdrantClient.upsert_calls.clear()
    FakeQdrantClient.set_payload_calls.clear()
    FakeQdrantClient.batch_payload_calls.clear()
    update_manual_metadata("default", "a", {"product_model": "A1"}, qdrant_library_config)

    task = start_library_rebuild(app, "default", qdrant_library_config, embedder=fake_embedder, mode="incremental")
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "done"
    assert task.qdrant_sync["points_upserted"] == 1
    assert task.qdrant_sync["points_reused"] == 2
    assert FakeQdrantClient.upsert_calls[-1] == ("test_default", [0])
    assert FakeQdrantClient.set_payload_calls == []
    assert len(FakeQdrantClient.batch_payload_calls) == 1
    assert FakeQdrantClient.batch_payload_calls[-1][0] == "test_default"
    assert [node_id for node_id, _payload in FakeQdrantClient.batch_payload_calls[-1][1]] == [1, 2]
    assert all(payload["build_id"] == app.get_current("default").build_id for _node_id, payload in FakeQdrantClient.batch_payload_calls[-1][1])
    assert all(payload["chunk_id"].startswith("chunk:sha256:") for _node_id, payload in FakeQdrantClient.batch_payload_calls[-1][1])
    assert {payload["doc_id"] for _node_id, payload in FakeQdrantClient.batch_payload_calls[-1][1]} == {"b", "c"}


def test_qdrant_incremental_rebuild_then_ann_search_regression(monkeypatch, tmp_path):
    FakeQdrantClient.reset()
    monkeypatch.setattr("tagmemorag.storage.qdrant_vector.QdrantVectorStore._create_client", lambda *args, **kwargs: FakeQdrantClient())
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        vector_store=VectorStoreConfig(provider="qdrant", collection_prefix="test"),
        search=SearchConfig(ann_preselect_enabled=True, ann_candidate_k=2, source_k=2, steps=0),
        model={"dim": KeywordEmbedder.dim},
    )
    embedder = KeywordEmbedder()
    upsert_manual(
        "default",
        _metadata("coffee/a.md", "a"),
        b"# Reused\nalpha stable reusable chunk.\n# Changed\ncharlie original chunk.\n",
        cfg,
    )
    upsert_manual("default", _metadata("coffee/b.md", "b"), b"# Removed\ndelta stale chunk.\n", cfg)
    old_state = build_kb(library_root("default", cfg), "default", cfg, embedder=embedder)
    _persist_qdrant_baseline(old_state, cfg)
    old_reused_vector = list(FakeQdrantClient.collections["test_default"][0].vector)
    app = AppState(old_state)
    FakeQdrantClient.upsert_calls.clear()
    FakeQdrantClient.set_payload_calls.clear()
    FakeQdrantClient.batch_payload_calls.clear()
    FakeQdrantClient.delete_calls.clear()

    (library_root("default", cfg) / "coffee" / "a.md").write_text(
        "# Reused\nalpha stable reusable chunk.\n# Changed\nbravo changed chunk.\n",
        encoding="utf-8",
    )
    mark_pending("default", cfg, dirty={"manual_id": "a", "source_file": "coffee/a.md", "operation": "file_replace"})
    delete_manual("default", "b", cfg)
    task = start_library_rebuild(app, "default", cfg, embedder=embedder, mode="incremental")
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "done"
    assert task.effective_mode == "incremental"
    assert task.qdrant_sync == {
        "provider": "qdrant",
        "strategy": "point_incremental",
        "points_upserted": 1,
        "points_deleted": 1,
        "points_reused": 1,
        "fallback_reason": "",
    }
    current_state = app.get_current("default")
    collection = FakeQdrantClient.collections["test_default"]
    assert sorted(collection) == [0, 1]
    assert FakeQdrantClient.upsert_calls[-1] == ("test_default", [1])
    assert FakeQdrantClient.set_payload_calls == []
    assert FakeQdrantClient.batch_payload_calls[-1][0] == "test_default"
    assert FakeQdrantClient.batch_payload_calls[-1][1][0][0] == 0
    assert FakeQdrantClient.delete_calls[-1] == ("test_default", [2])
    assert collection[0].vector == old_reused_vector
    assert collection[0].payload["build_id"] == current_state.build_id
    assert collection[1].payload["build_id"] == current_state.build_id

    collection[0].vector = [0.0, 1.0, 0.0, 0.0]
    collection[1].vector = [1.0, 0.0, 0.0, 0.0]
    execution = execute_search(
        state=current_state,
        query_vec=embedder.encode_query("alpha"),
        settings=cfg,
        top_k=2,
        source_k=2,
        steps=0,
        decay=cfg.search.decay,
        amplitude_cutoff=cfg.search.amplitude_cutoff,
        aggregate=cfg.search.aggregate,
    )

    current_node_ids = set(current_state.graph.nodes)
    assert execution.strategy == "ann_preselect_then_wave"
    assert execution.ann_candidate_count == 2
    assert set(FakeQdrantClient.search_calls[-1][2]) <= current_node_ids
    assert 2 not in FakeQdrantClient.search_calls[-1][2]
    assert [result.node_id for result in execution.results] == [0, 1]
    assert execution.results[0].text.startswith("Reused")


def test_qdrant_incremental_sync_falls_back_without_identity(qdrant_library_config, fake_embedder):
    upsert_manual("default", _metadata("coffee/a.md", "a"), b"# A\nSteam works.\n", qdrant_library_config)
    old_state = build_kb(library_root("default", qdrant_library_config), "default", qdrant_library_config, embedder=fake_embedder)
    _persist_qdrant_baseline(old_state, qdrant_library_config)
    app = AppState(old_state)
    update_manual_metadata("default", "a", {"product_model": "A1"}, qdrant_library_config)
    identity_file = Path(qdrant_library_config.storage.data_dir) / "default" / "chunk_identity.json"
    identity_file.unlink()

    task = start_library_rebuild(app, "default", qdrant_library_config, embedder=fake_embedder, mode="incremental")
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "done"
    assert task.effective_mode == "incremental"
    assert task.qdrant_sync["strategy"] == "full_sync"
    assert task.qdrant_sync["fallback_reason"] == "missing_chunk_identity"


def test_failed_qdrant_sync_keeps_pending_dirty_state(qdrant_library_config, fake_embedder):
    upsert_manual("default", _metadata("coffee/a.md", "a"), b"# A\nSteam works.\n", qdrant_library_config)
    old_state = build_kb(library_root("default", qdrant_library_config), "default", qdrant_library_config, embedder=fake_embedder)
    _persist_qdrant_baseline(old_state, qdrant_library_config)
    app = AppState(old_state)
    update_manual_metadata("default", "a", {"product_model": "A1"}, qdrant_library_config)
    FakeQdrantClient.fail_next_upsert = True

    task = start_library_rebuild(app, "default", qdrant_library_config, embedder=fake_embedder, mode="full")
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "failed"
    assert app.get_current("default").build_id == old_state.build_id
    assert load_manifest("default", qdrant_library_config).pending_changes is True
    assert FakeQdrantClient.delete_calls == []
    summary = task.to_dict()["operations_summary"]
    assert summary["status"] == "failed"
    assert summary["current_build_id"] == old_state.build_id
    assert summary["pending_changes"] is True
    assert summary["recovery_hint"] == "check_qdrant_then_retry"
    report = build_dirty_state_report("default", qdrant_library_config, graph_state=app.get_current("default"))
    assert "check_qdrant_then_retry" in report["recovery_actions"]

    FakeQdrantClient.fail_next_upsert = False
    recovery = start_library_rebuild(app, "default", qdrant_library_config, embedder=fake_embedder, mode="full")
    for _ in range(100):
        if recovery.status != "running":
            break
        time.sleep(0.01)

    assert recovery.status == "done"
    assert recovery.effective_mode == "full"
    assert load_manifest("default", qdrant_library_config).pending_changes is False
    assert app.get_current("default").build_id == recovery.build_id
    assert recovery.to_dict()["operations_summary"]["recovery_hint"] == "none"


def test_failed_reused_payload_refresh_blocks_stale_delete_and_graph_swap(monkeypatch, tmp_path):
    FakeQdrantClient.reset()
    monkeypatch.setattr("tagmemorag.storage.qdrant_vector.QdrantVectorStore._create_client", lambda *args, **kwargs: FakeQdrantClient())
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        vector_store=VectorStoreConfig(provider="qdrant", collection_prefix="test"),
        model={"dim": KeywordEmbedder.dim},
    )
    embedder = KeywordEmbedder()
    upsert_manual(
        "default",
        _metadata("coffee/a.md", "a"),
        b"# Reused\nalpha stable reusable chunk.\n# Changed\ncharlie original chunk.\n",
        cfg,
    )
    upsert_manual("default", _metadata("coffee/b.md", "b"), b"# Removed\ndelta stale chunk.\n", cfg)
    old_state = build_kb(library_root("default", cfg), "default", cfg, embedder=embedder)
    _persist_qdrant_baseline(old_state, cfg)
    app = AppState(old_state)
    FakeQdrantClient.upsert_calls.clear()
    FakeQdrantClient.batch_payload_calls.clear()
    FakeQdrantClient.delete_calls.clear()

    (library_root("default", cfg) / "coffee" / "a.md").write_text(
        "# Reused\nalpha stable reusable chunk.\n# Changed\nbravo changed chunk.\n",
        encoding="utf-8",
    )
    mark_pending("default", cfg, dirty={"manual_id": "a", "source_file": "coffee/a.md", "operation": "file_replace"})
    delete_manual("default", "b", cfg)
    FakeQdrantClient.fail_next_batch_payload = True

    task = start_library_rebuild(app, "default", cfg, embedder=embedder, mode="incremental")
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    assert task.status == "failed"
    assert app.get_current("default").build_id == old_state.build_id
    assert load_manifest("default", cfg).pending_changes is True
    assert FakeQdrantClient.upsert_calls[-1] == ("test_default", [1])
    assert FakeQdrantClient.delete_calls == []
    assert 2 in FakeQdrantClient.collections["test_default"]
