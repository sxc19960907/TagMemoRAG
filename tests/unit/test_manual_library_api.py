from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.config import ManualLibraryConfig, Settings, StorageConfig
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


def _metadata(manual_id: str = "cm1", source_file: str = "coffee/cm1.md") -> dict[str, object]:
    return {
        "manual_id": manual_id,
        "title": "CM1 Manual",
        "source_file": source_file,
        "product_category": "coffee",
        "language": "zh-CN",
        "tags": ["Maintenance Task"],
    }


def test_manual_validate_upload_list_conflict_and_update(tmp_path, fake_embedder):
    client = _configure(tmp_path, fake_embedder)
    metadata = _metadata()

    validate = client.post("/manuals/validate", json={"kb_name": "default", "metadata": metadata})
    assert validate.status_code == 200
    assert validate.json()["valid"] is True
    assert validate.json()["normalized"]["tags"] == ["maintenance-task"]

    upload = client.post(
        "/manuals",
        data={"kb_name": "default", "metadata": json.dumps(metadata)},
        files={"file": ("cm1.md", b"# Use\nClean weekly.\n", "text/markdown")},
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["record"]["manual_id"] == "cm1"
    assert body["rebuild_required"] is True

    conflict = client.post(
        "/manuals",
        data={"kb_name": "default", "metadata": json.dumps(metadata)},
        files={"file": ("cm1.md", b"# Use\nReplace.\n", "text/markdown")},
    )
    assert conflict.status_code == 400
    assert conflict.json()["code"] == "INVALID_REQUEST"

    listing = client.get("/manual-library", params={"kb_name": "default"}).json()
    assert listing["manuals"][0]["manual_id"] == "cm1"
    assert listing["manuals"][0]["searchable"] is False
    assert listing["manuals"][0]["rebuild_required"] is True

    update = client.patch(
        "/manuals/cm1/metadata",
        json={"kb_name": "default", "metadata": {"product_model": "CM1", "tags": ["Steam Wand"]}},
    )
    assert update.status_code == 200
    assert update.json()["record"]["product_model"] == "CM1"
    assert update.json()["record"]["tags"] == ["steam-wand"]


def test_manual_disable_hard_delete_and_library_rebuild(tmp_path, fake_embedder):
    client = _configure(tmp_path, fake_embedder)
    metadata = _metadata()
    client.post(
        "/manuals",
        data={"kb_name": "default", "metadata": json.dumps(metadata)},
        files={"file": ("cm1.md", b"# Use\nClean weekly.\n", "text/markdown")},
    )

    rebuild = client.post("/manual-library/rebuild", json={"kb_name": "default"})
    assert rebuild.status_code == 202
    task_id = rebuild.json()["task_id"]
    for _ in range(50):
        task = client.get(f"/rebuild/{task_id}").json()
        if task["status"] != "running":
            break
    assert task["status"] == "done"
    built = client.get("/manual-library", params={"kb_name": "default"}).json()["manuals"][0]
    assert built["searchable"] is True
    assert built["chunk_count"] == 1
    assert built["rebuild_required"] is False

    disabled = client.delete("/manuals/cm1", params={"kb_name": "default"})
    assert disabled.status_code == 200
    assert disabled.json()["record"]["status"] == "disabled"

    hard = client.delete("/manuals/cm1", params={"kb_name": "default", "hard": "true"})
    assert hard.status_code == 200
    assert hard.json()["status"] == "deleted"
    assert client.get("/manual-library", params={"kb_name": "default"}).json()["manuals"] == []
