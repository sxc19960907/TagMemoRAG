from __future__ import annotations

import json
import zipfile

import pytest

from tagmemorag.config import ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.errors import ServiceError
from tagmemorag.manual_bundle import export_bundle, import_bundle, inspect_bundle
from tagmemorag.manual_library import list_records, load_manifest, upsert_manual


def _cfg(tmp_path, *, registry: bool = False) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(
            root_dir=str(tmp_path / "manuals"),
            registry_backend="sqlite" if registry else "file",
            registry_path=str(tmp_path / "registry.sqlite3"),
            blob_backend="local",
            blob_root_dir=str(tmp_path / "blobs"),
        ),
        model={"dim": 64},
    )


def _metadata(source_file: str = "coffee/cm1.md", manual_id: str = "cm1") -> dict[str, object]:
    return {
        "manual_id": manual_id,
        "title": f"{manual_id.upper()} Manual",
        "source_file": source_file,
        "product_category": "coffee",
        "language": "zh-CN",
        "tags": ["Maintenance"],
    }


def test_export_inspect_and_import_file_sidecar_bundle(tmp_path):
    source_cfg = _cfg(tmp_path / "source")
    target_cfg = _cfg(tmp_path / "target")
    upsert_manual("default", _metadata(), b"# Use\nClean weekly.\n", source_cfg)
    bundle = tmp_path / "default.bundle.zip"

    exported = export_bundle("default", source_cfg, bundle)

    assert exported.manual_count == 1
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert "tagmemorag-bundle.json" in names
        assert "checksums.json" in names
        assert "records/cm1.json" in names
        assert any(name.startswith("blobs/cm1/1/") for name in names)
        manifest = json.loads(archive.read("tagmemorag-bundle.json"))
        assert manifest["source"]["registry_backend"] == "file"
        assert manifest["counts"]["manual_count"] == 1

    inspected = inspect_bundle(bundle, target_cfg, target_kb="restored")
    assert inspected.valid is True
    assert inspected.checksum_verified is True
    assert inspected.counts["manual_count"] == 1
    assert inspected.import_actions[0].action == "create"

    dry_run = import_bundle(bundle, target_cfg, target_kb="restored", dry_run=True)
    assert dry_run.dry_run is True
    assert dry_run.imported_count == 0
    assert not list_records("restored", target_cfg)

    result = import_bundle(bundle, target_cfg, target_kb="restored")

    assert result.imported_count == 1
    records = list_records("restored", target_cfg)
    assert len(records) == 1
    assert records[0].manual_id == "cm1"
    assert records[0].checksum
    manifest = load_manifest("restored", target_cfg)
    assert manifest.pending_changes is True
    assert manifest.dirty_manuals["cm1"].operation == "bundle_import"


def test_import_conflict_modes(tmp_path):
    source_cfg = _cfg(tmp_path / "source")
    target_cfg = _cfg(tmp_path / "target")
    upsert_manual("default", _metadata(), b"# Use\nClean weekly.\n", source_cfg)
    upsert_manual("default", _metadata(), b"# Existing\nDifferent.\n", target_cfg)
    bundle = tmp_path / "default.bundle.zip"
    export_bundle("default", source_cfg, bundle)

    inspected = inspect_bundle(bundle, target_cfg, conflict_mode="fail")
    assert inspected.valid is True
    assert inspected.conflicts[0].conflict_type == "manual_id"
    assert inspected.import_actions[0].action == "conflict"

    with pytest.raises(ServiceError) as failed:
        import_bundle(bundle, target_cfg, conflict_mode="fail")
    assert failed.value.code == "INVALID_REQUEST"

    skipped = import_bundle(bundle, target_cfg, conflict_mode="skip")
    assert skipped.skipped_count == 1
    assert list_records("default", target_cfg)[0].checksum != list_records("default", source_cfg)[0].checksum

    overwritten = import_bundle(bundle, target_cfg, conflict_mode="overwrite")
    assert overwritten.imported_count == 1
    assert list_records("default", target_cfg)[0].checksum == list_records("default", source_cfg)[0].checksum


def test_import_overwrite_replaces_source_file_conflict(tmp_path):
    source_cfg = _cfg(tmp_path / "source")
    target_cfg = _cfg(tmp_path / "target", registry=True)
    upsert_manual("default", _metadata("coffee/cm1.md", "cm1"), b"# Use\nClean weekly.\n", source_cfg)
    upsert_manual("default", _metadata("coffee/cm1.md", "old-cm1"), b"# Existing\nDifferent.\n", target_cfg)
    bundle = tmp_path / "default.bundle.zip"
    export_bundle("default", source_cfg, bundle)

    inspected = inspect_bundle(bundle, target_cfg, conflict_mode="overwrite")
    assert inspected.conflicts[0].conflict_type == "source_file"
    assert inspected.import_actions[0].action == "overwrite"

    result = import_bundle(bundle, target_cfg, conflict_mode="overwrite")

    assert result.imported_count == 1
    records = list_records("default", target_cfg)
    assert [record.manual_id for record in records] == ["cm1"]
    assert records[0].checksum == list_records("default", source_cfg)[0].checksum


def test_inspect_rejects_unsafe_path_and_checksum_mismatch(tmp_path):
    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../escape.json", "{}")
    unsafe_report = inspect_bundle(unsafe)
    assert unsafe_report.valid is False
    assert unsafe_report.errors[0]["code"] == "INVALID_INPUT"

    cfg = _cfg(tmp_path / "source")
    upsert_manual("default", _metadata(), b"# Use\nClean weekly.\n", cfg)
    bundle = tmp_path / "default.bundle.zip"
    export_bundle("default", cfg, bundle)
    corrupted = tmp_path / "corrupted.bundle.zip"
    with zipfile.ZipFile(bundle) as src, zipfile.ZipFile(corrupted, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name.startswith("records/"):
                data = data.replace(b"CM1 Manual", b"Changed Manual")
            dst.writestr(name, data)

    report = inspect_bundle(corrupted)
    assert report.valid is False
    assert report.errors[0]["code"] == "INVALID_INPUT"
    assert "checksum" in report.errors[0]["message"].lower()


def test_export_registry_bundle_reads_blob_store_and_audit(tmp_path):
    cfg = _cfg(tmp_path, registry=True)
    upsert_manual("default", _metadata(), b"# Use\nClean weekly.\n", cfg)
    bundle = tmp_path / "registry.bundle.zip"

    exported = export_bundle("default", cfg, bundle)

    assert exported.manual_count == 1
    assert exported.audit_event_count == 1
    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("tagmemorag-bundle.json"))
        record = json.loads(archive.read("records/cm1.json"))
        assert manifest["source"]["registry_backend"] == "sqlite"
        assert manifest["source"]["blob_backend"] == "local"
        assert record["blob"]["source_backend"] == "local"
        assert not any(str(value).startswith("/") for value in record["blob"].values())
        assert "audit/events.jsonl" in archive.namelist()

    report = inspect_bundle(bundle, cfg)
    assert report.valid is True
    assert report.counts["audit_event_count"] == 1
