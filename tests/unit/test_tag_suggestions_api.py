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


def test_suggest_tags_api_returns_scored_normalized_suggestions(tmp_path, fake_embedder):
    client = _configure(tmp_path, fake_embedder)
    existing = {
        "manual_id": "cm0",
        "title": "CM0 Coffee Maintenance",
        "source_file": "coffee/cm0.md",
        "product_category": "coffee",
        "tags": ["maintenance"],
    }
    client.post(
        "/manuals",
        data={"kb_name": "default", "metadata": json.dumps(existing)},
        files={"file": ("cm0.md", b"# Use\nClean weekly.\n", "text/markdown")},
    )

    response = client.post(
        "/manuals/tags/suggest",
        json={
            "kb_name": "default",
            "metadata": {
                "manual_id": "cm1",
                "title": "CM1 Coffee Maintenance",
                "source_file": "coffee/cm1-maintenance.md",
                "product_category": "coffee",
                "tags": ["coffee"],
            },
            "limit": 5,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["kb_name"] == "default"
    assert body["existing_tags"] == ["maintenance"]
    suggestions = body["suggestions"]
    assert any(item["tag"] == "maintenance" and item["score"] > 0 for item in suggestions)
    assert all(item["tag"] != "coffee" for item in suggestions)
    assert {"tag", "label", "score", "sources", "reason"} <= suggestions[0].keys()


def test_suggest_tags_api_validates_limit(tmp_path, fake_embedder):
    client = _configure(tmp_path, fake_embedder)

    response = client.post(
        "/manuals/tags/suggest",
        json={"kb_name": "default", "metadata": {}, "limit": 0},
    )

    assert response.status_code == 422
