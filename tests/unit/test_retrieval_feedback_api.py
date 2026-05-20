from __future__ import annotations

from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.auth.config_store import ConfigAuthStore
from tagmemorag.config import ApiKeyConfig, AuthConfig, Settings, StorageConfig
from tagmemorag.state import AppState


def _client(tmp_path, fake_embedder, *, auth: bool = False) -> TestClient:
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
        auth=AuthConfig(
            enabled=auth,
            keys=[
                ApiKeyConfig(
                    id="reader",
                    hash=ConfigAuthStore.hash_plaintext("tmr_live_reader"),
                    kb_allowlist=["default"],
                    scopes=["search"],
                ),
                ApiKeyConfig(
                    id="admin",
                    hash=ConfigAuthStore.hash_plaintext("tmr_live_admin"),
                    kb_allowlist=["default"],
                    scopes=["search", "admin"],
                ),
            ],
        ),
    )
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState()
    api.app_state.auth_store = ConfigAuthStore.from_config(cfg.auth)
    return TestClient(api.app)


def _payload():
    return {
        "kb_name": "default",
        "trace_id": "trace-1",
        "search_id": "search-1",
        "retrieve_id": "retrieve-1",
        "build_id": "build-1",
        "query": "E05 蒸汽异常怎么处理",
        "outcome": "missing_result",
        "selected_evidence_ids": ["ev_001"],
        "selected_context_item_ids": ["ctx_001"],
        "answerable": False,
        "failure_reason": "no_results",
        "expected": [{"source_file": "coffee.md", "header": "E05", "metadata": {"manual_id": "cm1"}}],
    }


def test_feedback_api_submit_list_review_and_preview(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    created = client.post("/search/feedback", json=_payload())
    assert created.status_code == 200
    feedback_id = created.json()["feedback"]["feedback_id"]

    listed = client.get("/search/feedback", params={"kb_name": "default", "status": "new"})
    assert listed.status_code == 200
    assert [row["feedback_id"] for row in listed.json()["feedback"]] == [feedback_id]

    reviewed = client.patch(
        f"/search/feedback/{feedback_id}",
        json={"kb_name": "default", "status": "triaged", "operator_note": "Promote this."},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["feedback"]["status"] == "triaged"

    preview = client.post(
        "/search/feedback/promote/preview",
        json={"kb_name": "default", "feedback_ids": [feedback_id]},
    )
    assert preview.status_code == 200
    assert preview.json()["cases"][0]["id"] == f"feedback-{feedback_id}"


def test_retrieve_feedback_api_submit_alias_persists_retrieve_fields(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    created = client.post("/retrieve/feedback", json=_payload())

    assert created.status_code == 200
    feedback = created.json()["feedback"]
    assert feedback["retrieve_id"] == "retrieve-1"
    assert feedback["selected_evidence_ids"] == ["ev_001"]
    assert feedback["selected_context_item_ids"] == ["ctx_001"]
    assert feedback["answerable"] is False
    assert feedback["failure_reason"] == "no_results"


def test_feedback_api_auth_scopes(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder, auth=True)

    created = client.post(
        "/retrieve/feedback",
        headers={"Authorization": "Bearer tmr_live_reader"},
        json=_payload(),
    )
    assert created.status_code == 200

    forbidden = client.get(
        "/search/feedback",
        headers={"Authorization": "Bearer tmr_live_reader"},
        params={"kb_name": "default"},
    )
    assert forbidden.status_code == 403

    allowed = client.get(
        "/search/feedback",
        headers={"Authorization": "Bearer tmr_live_admin"},
        params={"kb_name": "default"},
    )
    assert allowed.status_code == 200
