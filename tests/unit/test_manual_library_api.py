from __future__ import annotations

import json

from fastapi.testclient import TestClient
import networkx as nx
import numpy as np

from tagmemorag import api
from tagmemorag.config import ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.state import AppState
from tagmemorag.types import GraphState


def _configure(tmp_path, fake_embedder) -> TestClient:
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        model={"dim": 64},
    )
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState()
    api.rebuild_queue = None
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
    assert listing["pending_changes"] is True
    assert listing["dirty_manual_count"] == 1
    assert listing["dirty_manuals"][0]["manual_id"] == "cm1"

    update = client.patch(
        "/manuals/cm1/metadata",
        json={"kb_name": "default", "metadata": {"product_model": "CM1", "tags": ["Steam Wand"]}},
    )
    assert update.status_code == 200
    assert update.json()["record"]["product_model"] == "CM1"
    assert update.json()["record"]["tags"] == ["steam-wand"]

    dirty = client.get("/manual-library/dirty", params={"kb_name": "default"})
    assert dirty.status_code == 200
    dirty_body = dirty.json()
    assert dirty_body["pending_changes"] is True
    assert dirty_body["current_build_id"] == ""
    assert dirty_body["recovery_actions"] == ["inspect_dirty", "retry_incremental", "force_full_rebuild"]
    assert dirty_body["operations_summary"]["recovery_hint"] == "inspect_dirty"
    assert dirty_body["dirty_manuals"][0]["manual_id"] == "cm1"
    assert dirty_body["dirty_manuals"][0]["status"] == "active"

    dirty_csv = client.get("/manual-library/dirty", params={"kb_name": "default", "format": "csv"})
    assert dirty_csv.status_code == 200
    assert "manual_id,source_file,operation" in dirty_csv.text


def test_manual_disable_hard_delete_and_library_rebuild(tmp_path, fake_embedder):
    client = _configure(tmp_path, fake_embedder)
    metadata = _metadata()
    client.post(
        "/manuals",
        data={"kb_name": "default", "metadata": json.dumps(metadata)},
        files={"file": ("cm1.md", b"# Use\nClean weekly.\n", "text/markdown")},
    )

    rebuild = client.post("/manual-library/rebuild", json={"kb_name": "default", "mode": "incremental"})
    assert rebuild.status_code == 202
    assert rebuild.json()["requested_mode"] == "incremental"
    task_id = rebuild.json()["task_id"]
    for _ in range(50):
        task = client.get(f"/rebuild/{task_id}").json()
        if task["status"] != "running":
            break
    assert task["status"] == "done"
    assert task["effective_mode"] in {"full", "incremental"}
    assert "dirty_manual_count" in task
    assert "impact_summary" in task
    assert task["operations_summary"]["status"] == "done"
    assert task["operations_summary"]["current_build_id"] == task["build_id"]
    assert task["operations_summary"]["pending_changes"] is False
    assert task["operations_summary"]["recovery_hint"] == "none"
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


def test_manual_library_rebuild_queue_api(tmp_path, fake_embedder):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals"), rebuild_queue_enabled=True),
        model={"dim": 64},
    )
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState()
    api.rebuild_queue = None
    client = TestClient(api.app)
    client.post(
        "/manuals",
        data={"kb_name": "default", "metadata": json.dumps(_metadata())},
        files={"file": ("cm1.md", b"# Use\nClean weekly.\n", "text/markdown")},
    )

    rebuild = client.post("/manual-library/rebuild", json={"kb_name": "default", "mode": "incremental"})

    assert rebuild.status_code == 202
    body = rebuild.json()
    assert body["job_id"]
    assert body["status"] in {"queued", "running", "succeeded"}
    listed = client.get("/manual-library/rebuild-jobs", params={"kb_name": "default"})
    assert listed.status_code == 200
    assert listed.json()["jobs"][0]["job_id"] == body["job_id"]


def test_manual_library_diagnostics_file_sidecar_and_queue_disabled(tmp_path, fake_embedder):
    client = _configure(tmp_path, fake_embedder)

    response = client.get("/manual-library/diagnostics", params={"kb_name": "default"})

    assert response.status_code == 200
    body = response.json()
    assert body["registry"]["enabled"] is False
    assert body["blob_health"]["checked"] is False
    assert body["rebuild_queue"]["enabled"] is False
    assert body["dirty"]["pending_changes"] is False
    assert body["recommendations"][0]["code"] == "file_sidecar_mode"


def test_manual_library_diagnostics_returns_pdf_quality_summary(tmp_path, fake_embedder):
    client = _configure(tmp_path, fake_embedder)
    api.app_state.swap_kb(
        "default",
        GraphState(
            graph=nx.Graph(),
            vectors=np.zeros((0, 64), dtype=np.float32),
            kb_name="default",
            meta={
                "pdf_quality": {
                    "documents": 1,
                    "pages_total": 3,
                    "pages_with_text": 2,
                    "pages_missing_text": 1,
                    "ocr_pages_created": 0,
                    "warning_counts": {"rotated_text": 2},
                }
            },
        ),
    )

    response = client.get("/manual-library/diagnostics", params={"kb_name": "default"})

    assert response.status_code == 200
    body = response.json()
    assert body["last_rebuild"]["pdf_quality"]["pages_total"] == 3
    assert body["last_rebuild"]["pdf_quality"]["pages_missing_text"] == 1
    assert body["last_rebuild"]["pdf_quality"]["warning_counts"] == {"rotated_text": 2}
    assert any(item["code"] == "review_pdf_quality" for item in body["recommendations"])


def test_manual_library_diagnostics_registry_blob_verify_audit_and_queue(tmp_path, fake_embedder):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(
            root_dir=str(tmp_path / "manuals"),
            registry_backend="sqlite",
            registry_path=str(tmp_path / "registry.sqlite"),
            blob_root_dir=str(tmp_path / "blobs"),
            rebuild_queue_enabled=True,
        ),
        model={"dim": 64},
    )
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState()
    api.rebuild_queue = None
    client = TestClient(api.app)
    client.post(
        "/manuals",
        data={"kb_name": "default", "metadata": json.dumps(_metadata())},
        files={"file": ("cm1.md", b"# Use\nClean weekly.\n", "text/markdown")},
    )
    listing = client.get("/manual-library", params={"kb_name": "default"}).json()
    blob_key = listing["manuals"][0]["blob_key"]
    (tmp_path / "blobs" / blob_key).unlink()
    rebuild = client.post("/manual-library/rebuild", json={"kb_name": "default", "mode": "auto"})
    assert rebuild.status_code == 202

    diagnostics = client.get(
        "/manual-library/diagnostics",
        params={"kb_name": "default", "verify_blobs": "true"},
    )

    assert diagnostics.status_code == 200
    body = diagnostics.json()
    assert body["registry"]["enabled"] is True
    assert body["registry"]["record_count"] == 1
    assert body["blob_health"]["checked"] is True
    assert body["blob_health"]["missing_count"] == 1
    assert body["blob_health"]["missing"][0]["manual_id"] == "cm1"
    assert body["rebuild_queue"]["enabled"] is True
    assert body["rebuild_queue"]["jobs"][0]["job_id"] == rebuild.json()["job_id"]
    assert any(item["code"] == "restore_object_store" for item in body["recommendations"])

    audit = client.get("/manual-library/registry/audit", params={"kb_name": "default", "manual_id": "cm1", "limit": "500"})
    assert audit.status_code == 200
    audit_body = audit.json()
    assert audit_body["enabled"] is True
    assert audit_body["limit"] == 200
    assert audit_body["events"][0]["manual_id"] == "cm1"
    assert audit_body["events"][0]["operation"] == "upsert"
    assert set(audit_body["events"][0]["detail"]) <= {"source_file", "status", "checksum", "blob_backend", "size_bytes", "content_type"}


def test_tag_governance_api_policy_stats_and_rewrite(tmp_path, fake_embedder):
    client = _configure(tmp_path, fake_embedder)
    client.post(
        "/manuals",
        data={"kb_name": "default", "metadata": json.dumps(_metadata("cm1", "coffee/cm1.md") | {"tags": ["cleaning"]})},
        files={"file": ("cm1.md", b"# Clean\n", "text/markdown")},
    )

    policy = client.put(
        "/manual-library/tags/policy",
        json={
            "kb_name": "default",
            "policy": {
                "canonical_tags": [{"tag": "maintenance"}],
                "synonyms": {"cleaning": "maintenance"},
            },
        },
    )
    assert policy.status_code == 200
    assert policy.json()["policy"]["synonyms"] == {"cleaning": "maintenance"}

    validation = client.post("/manuals/validate", json={"kb_name": "default", "metadata": _metadata("cm2", "coffee/cm2.md") | {"tags": ["cleaning"]}})
    assert validation.status_code == 200
    assert validation.json()["messages"][0]["code"] == "TAG_SYNONYM_USED"

    stats = client.get("/manual-library/tags", params={"kb_name": "default"})
    assert stats.status_code == 200
    assert stats.json()["stats"][0]["state"] == "synonym"
    assert stats.json()["issues"][0]["code"] == "SYNONYM_IN_USE"

    preview = client.post(
        "/manual-library/tags/rewrite/preview",
        json={"kb_name": "default", "source_tags": ["cleaning"], "target_tag": "maintenance"},
    )
    assert preview.status_code == 200
    assert preview.json()["affected_count"] == 1

    commit = client.post(
        "/manual-library/tags/rewrite",
        json={"kb_name": "default", "source_tags": ["cleaning"], "target_tag": "maintenance"},
    )
    assert commit.status_code == 200
    assert commit.json()["updated_count"] == 1
    listing = client.get("/manual-library", params={"kb_name": "default"}).json()
    assert listing["manuals"][0]["tags"] == ["maintenance"]
