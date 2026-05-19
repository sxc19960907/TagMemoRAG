from __future__ import annotations

from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.config import Settings, StorageConfig
from tagmemorag.connectors.materialize import materialize_connector_records
from tagmemorag.connectors.provider import fixture_markdown_record
from tagmemorag.state import AppState, build_kb


def test_materialized_connector_doc_is_retrievable(tmp_path, fake_embedder):
    cfg = Settings(storage=StorageConfig(data_dir=str(tmp_path / "data")), model={"dim": 64})
    record = fixture_markdown_record(
        manual_id="connector-reset",
        source_file="connector/reset.md",
        title="Connector Reset",
        text="# Reset Button\nHold the connector reset button for three seconds.",
    )
    materialize_connector_records((record,), kb_name="default", root_dir=tmp_path / "connector_docs", provider="fixture")
    docs_root = tmp_path / "connector_docs" / "default"
    state = build_kb(docs_root, "default", cfg, embedder=fake_embedder)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/retrieve", json={"question": "connector reset button", "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["answerability"]["answerable"] is True
    assert "connector reset button" in body["context_pack"]["items"][0]["content"].lower()
    assert body["results"][0]["manual_id"] == "connector-reset"


def test_materialized_connector_tombstone_is_skipped_by_rebuild(tmp_path, fake_embedder):
    cfg = Settings(storage=StorageConfig(data_dir=str(tmp_path / "data")), model={"dim": 64})
    tombstone = fixture_markdown_record(
        manual_id="connector-deleted",
        source_file="connector/deleted.md",
        title="Deleted",
        text="# Deleted\nShould not index.",
        action="delete",
    )
    materialize_connector_records((tombstone,), kb_name="default", root_dir=tmp_path / "connector_docs", provider="fixture")

    state = build_kb(tmp_path / "connector_docs" / "default", "default", cfg, embedder=fake_embedder)

    assert state.graph.number_of_nodes() == 0
