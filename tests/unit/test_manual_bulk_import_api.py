from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.auth.config_store import ConfigAuthStore
from tagmemorag.config import ApiKeyConfig, AuthConfig, ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.state import AppState


def _configure(tmp_path, fake_embedder) -> TestClient:
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        model={"dim": 64},
    )
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState()
    return TestClient(api.app)


def _metadata() -> list[dict[str, object]]:
    return [
        {
            "manual_id": "cm1",
            "title": "CM1 Manual",
            "source_file": "coffee/cm1.md",
            "product_category": "coffee",
            "language": "zh-CN",
            "tags": ["Maintenance Task"],
        }
    ]


def test_bulk_preview_api_returns_conflict_table_shape(tmp_path, fake_embedder):
    client = _configure(tmp_path, fake_embedder)

    response = client.post(
        "/manual-library/bulk/preview",
        data={"kb_name": "default", "metadata_format": "json", "metadata": json.dumps(_metadata())},
        files=[("files", ("cm1.md", b"# Use\nClean weekly.\n", "text/markdown"))],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["valid_count"] == 1
    assert body["rows"][0].keys() >= {"row", "manual_id", "source_file", "tag", "status", "action", "severity", "message"}
    assert body["rows"][0]["manual_id"] == "cm1"
    assert body["rows"][0]["tag"] == "maintenance-task"
    assert body["rows"][0]["action"] == "create"


def test_bulk_import_api_writes_and_marks_rebuild_required(tmp_path, fake_embedder):
    client = _configure(tmp_path, fake_embedder)

    response = client.post(
        "/manual-library/bulk/import",
        data={"kb_name": "default", "metadata_format": "json", "metadata": json.dumps(_metadata())},
        files=[("files", ("cm1.md", b"# Use\nClean weekly.\n", "text/markdown"))],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["imported_count"] == 1
    assert body["rebuild_required"] is True

    listing = client.get("/manual-library", params={"kb_name": "default"}).json()
    assert listing["manuals"][0]["manual_id"] == "cm1"
    assert listing["manuals"][0]["rebuild_required"] is True


def test_bulk_import_api_rejects_selected_invalid_row(tmp_path, fake_embedder):
    client = _configure(tmp_path, fake_embedder)
    metadata = [
        {
            "manual_id": "bad",
            "title": "Bad",
            "source_file": "../escape.md",
            "product_category": "coffee",
            "language": "zh-CN",
        }
    ]

    response = client.post(
        "/manual-library/bulk/import",
        data={
            "kb_name": "default",
            "metadata_format": "json",
            "metadata": json.dumps(metadata),
            "selected_rows": "[1]",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_INPUT"


def test_bulk_import_api_requires_write_scope_when_auth_enabled(tmp_path, fake_embedder):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        model={"dim": 64},
        auth=AuthConfig(
            enabled=True,
            keys=[
                ApiKeyConfig(
                    id="reader",
                    hash=ConfigAuthStore.hash_plaintext("tmr_live_reader"),
                    kb_allowlist=["default"],
                    scopes=["search"],
                ),
                ApiKeyConfig(
                    id="writer",
                    hash=ConfigAuthStore.hash_plaintext("tmr_live_writer"),
                    kb_allowlist=["default"],
                    scopes=["search", "rebuild"],
                ),
            ],
        ),
    )
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState()
    api.app_state.auth_store = ConfigAuthStore.from_config(cfg.auth)
    client = TestClient(api.app)

    data = {"kb_name": "default", "metadata_format": "json", "metadata": json.dumps(_metadata())}
    files = [("files", ("cm1.md", b"# Use\n", "text/markdown"))]

    preview = client.post(
        "/manual-library/bulk/preview",
        headers={"Authorization": "Bearer tmr_live_reader"},
        data=data,
        files=files,
    )
    assert preview.status_code == 200

    forbidden = client.post(
        "/manual-library/bulk/import",
        headers={"Authorization": "Bearer tmr_live_reader"},
        data=data,
        files=files,
    )
    assert forbidden.status_code == 403

    allowed = client.post(
        "/manual-library/bulk/import",
        headers={"Authorization": "Bearer tmr_live_writer"},
        data=data,
        files=files,
    )
    assert allowed.status_code == 200
