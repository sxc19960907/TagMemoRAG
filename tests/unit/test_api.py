from __future__ import annotations

from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.state import AppState, build_kb


def test_api_search_and_anchor(tmp_path, test_config, fake_embedder, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/search", json={"question": "蒸汽很小", "top_k": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["build_id"] == state.build_id
    assert body["results"]
    assert "search_time_ms" in body and body["search_time_ms"] >= 0

    anchor_response = client.post("/anchor", json={"node_id": 0, "label": "蒸汽重点"})
    assert anchor_response.status_code == 200
    anchor_key = anchor_response.json()["anchor_key"]
    assert client.get("/anchor").json()["anchors"][0]["anchor_key"] == anchor_key
    assert client.delete(f"/anchor/{anchor_key}").status_code == 200


def test_api_search_accepts_steps_decay_override(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post(
        "/search",
        json={"question": "蒸汽", "top_k": 2, "steps": 0, "decay": 0.5, "aggregate": "sum"},
    )
    assert response.status_code == 200
    assert response.json()["results"]


def test_api_anchor_add_invalid_node_returns_400(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/anchor", json={"node_id": 999, "label": "bad"})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_INPUT"


def test_api_unexpected_exception_wrapped_as_internal(tmp_path, test_config, fake_embedder, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app, raise_server_exceptions=False)

    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(api, "wave_search", boom)
    response = client.post("/search", json={"question": "x"})
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "INTERNAL"
    assert set(body) == {"code", "message", "detail"}


def test_api_error_format_when_kb_not_loaded(test_config, fake_embedder):
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState()
    client = TestClient(api.app)

    response = client.post("/search", json={"question": "蒸汽很小"})
    assert response.status_code == 404
    assert response.json()["code"] == "KB_NOT_LOADED"
    assert set(response.json()) == {"code", "message", "detail"}


def test_api_rebuild_and_graph_info(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState()
    client = TestClient(api.app)

    response = client.post("/rebuild", json={"docs_dir": str(docs)})
    assert response.status_code == 202
    task_id = response.json()["task_id"]
    for _ in range(50):
        task = client.get(f"/rebuild/{task_id}").json()
        if task["status"] != "running":
            break
    assert task["status"] == "done"
    info = client.get("/graph_info").json()
    assert info["node_count"] == 2
    assert info["build_id"]
