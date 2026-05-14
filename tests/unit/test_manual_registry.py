from __future__ import annotations

import pytest

from tagmemorag.errors import ServiceError
from tagmemorag.manual_blob_store import BlobRef
from tagmemorag.manual_registry import SQLiteManualRegistry
from tagmemorag.manuals import ManualMetadata


def _metadata(manual_id: str = "cm1", source_file: str = "coffee/cm1.md") -> ManualMetadata:
    return ManualMetadata(
        manual_id=manual_id,
        title="CM1",
        source_file=source_file,
        product_category="coffee",
        language="zh-CN",
    )


def _blob(key: str = "default/cm1/1/hash-cm1.md") -> BlobRef:
    return BlobRef(backend="local", blob_key=key, checksum="abc123", size_bytes=12, content_type="text/markdown")


def test_sqlite_registry_crud_and_audit(tmp_path):
    registry = SQLiteManualRegistry(tmp_path / "registry.sqlite3")

    created = registry.upsert("default", _metadata(), _blob(), operation="upload", actor_id="alice")
    updated = registry.update_metadata("default", "cm1", _metadata(source_file="coffee/new.md"), actor_id="bob")
    disabled = registry.set_status("default", "cm1", "disabled", operation="disable")

    assert created.version == 1
    assert updated.source_file == "coffee/new.md"
    assert disabled.status == "disabled"
    assert registry.get("default", "cm1").status == "disabled"
    assert [record.manual_id for record in registry.list("default")] == ["cm1"]
    assert [event.operation for event in registry.audit_events("default", "cm1")] == ["upload", "metadata_update", "disable"]


def test_sqlite_registry_enforces_source_file_uniqueness(tmp_path):
    registry = SQLiteManualRegistry(tmp_path / "registry.sqlite3")
    registry.upsert("default", _metadata("a", "manuals/a.md"), _blob("default/a/1/hash-a.md"), operation="upload")

    with pytest.raises(ServiceError) as exc:
        registry.upsert("default", _metadata("b", "manuals/a.md"), _blob("default/b/1/hash-b.md"), operation="upload")

    assert exc.value.code == "INVALID_REQUEST"
