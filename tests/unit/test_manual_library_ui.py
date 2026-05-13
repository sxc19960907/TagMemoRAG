from __future__ import annotations

from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.config import ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.state import AppState


def _client(tmp_path, fake_embedder) -> TestClient:
    api.settings = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        model={"dim": 64},
    )
    api.embedder = fake_embedder
    api.app_state = AppState()
    return TestClient(api.app)


def test_manual_library_admin_route_serves_shell(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    response = client.get("/admin/manual-library?kb_name=ops")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Manual Library" in body
    assert 'id="manual-rows"' in body
    assert 'id="suggest-upload-tags"' in body
    assert 'id="suggest-detail-tags"' in body
    assert 'id="bulk-preview-rows"' in body
    assert 'id="open-tag-governance"' in body
    assert 'id="tag-stat-rows"' in body
    assert 'id="rewrite-preview-rows"' in body
    assert '"defaultKbName": "ops"' in body
    assert "/static/manual-library/manual_library.js" in body


def test_manual_library_static_assets_are_served(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    css = client.get("/static/manual-library/manual_library.css")
    js = client.get("/static/manual-library/manual_library.js")

    assert css.status_code == 200
    assert "workspace" in css.text
    assert "suggestion-chip" in css.text
    assert js.status_code == 200
    assert "manuals/validate" in js.text
    assert "manuals/tags/suggest" in js.text
    assert "manual-library/bulk/preview" in js.text
    assert "manual-library/bulk/import" in js.text
    assert "manual-library/tags/rewrite/preview" in js.text
    assert "manual-library/tags/policy" in js.text
    assert "acceptAllSuggestions" in js.text


def test_retrieval_quality_admin_route_serves_shell(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    response = client.get("/admin/retrieval-quality?kb_name=ops")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Retrieval Quality" in body
    assert 'id="quality-feedback-rows"' in body
    assert 'id="quality-promotion-preview"' in body
    assert '"defaultKbName": "ops"' in body
    assert "/static/manual-library/retrieval_quality.js" in body


def test_retrieval_quality_static_asset_is_served(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    js = client.get("/static/manual-library/retrieval_quality.js")

    assert js.status_code == 200
    assert "/search/feedback" in js.text
    assert "/search/feedback/promote/preview" in js.text
    assert "quality-feedback-rows" in js.text
