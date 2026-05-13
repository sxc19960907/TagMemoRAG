from __future__ import annotations

from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.config import VectorStoreConfig
from tagmemorag.state import AppState, build_kb, save_kb
from tests.unit.test_storage_state import FakeQdrantClient


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
    assert body["search_id"]
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


def test_api_search_filters_by_manual_metadata(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    (docs / "fridge").mkdir(parents=True)
    (docs / "coffee").mkdir()
    (docs / "fridge" / "manual.md").write_text("# 温度\n冷藏室温度可以调节。\n", encoding="utf-8")
    (docs / "fridge" / "manual.metadata.json").write_text(
        '{"manual_id":"fridge-manual","title":"Fridge Manual","source_file":"fridge/manual.md","product_category":"fridge","product_model":"NRK6192","language":"zh-CN","tags":["temperature-setting"]}',
        encoding="utf-8",
    )
    (docs / "coffee" / "manual.md").write_text("# 温度\n咖啡温度和蒸汽设置。\n", encoding="utf-8")
    (docs / "coffee" / "manual.metadata.json").write_text(
        '{"manual_id":"coffee-manual","title":"Coffee Manual","source_file":"coffee/manual.md","product_category":"coffee","product_model":"CM1","language":"zh-CN","tags":["maintenance"]}',
        encoding="utf-8",
    )
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post(
        "/search",
        json={
            "question": "温度",
            "top_k": 5,
            "filters": {"product_category": "fridge", "product_model": "NRK6192", "tags": ["Temperature Setting"]},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"]
    assert {result["manual_id"] for result in body["results"]} == {"fridge-manual"}

    no_match = client.post("/search", json={"question": "温度", "filters": {"product_model": "missing"}})
    assert no_match.status_code == 200
    assert no_match.json()["results"] == []


def test_api_manuals_lists_metadata_facets(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    (docs / "fridge").mkdir(parents=True)
    (docs / "fridge" / "manual.md").write_text("# 温度\n冷藏室温度可以调节。\n# 维护\n清理排水孔。\n", encoding="utf-8")
    (docs / "fridge" / "manual.metadata.json").write_text(
        '{"manual_id":"fridge-manual","title":"Fridge Manual","source_file":"fridge/manual.md","brand":"Gorenje","product_category":"fridge","product_model":"NRK6192","language":"zh-CN","tags":["temperature-setting","maintenance"]}',
        encoding="utf-8",
    )
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.get("/manuals")

    assert response.status_code == 200
    body = response.json()
    assert body["kb_name"] == "default"
    assert body["manuals"] == [
        {
            "manual_id": "fridge-manual",
            "title": "Fridge Manual",
            "source_file": "fridge/manual.md",
            "brand": "Gorenje",
            "product_category": "fridge",
            "product_name": "",
            "product_model": "NRK6192",
            "language": "zh-CN",
            "version": "",
            "tags": ["temperature-setting", "maintenance"],
            "chunk_count": 2,
        }
    ]
    assert body["facets"]["brand"] == ["Gorenje"]
    assert body["facets"]["product_category"] == ["fridge"]
    assert body["facets"]["tags"] == ["maintenance", "temperature-setting"]


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

    monkeypatch.setattr(api, "execute_search", boom)
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


def test_api_search_uses_ann_preselection_with_qdrant(monkeypatch, tmp_path, test_config, fake_embedder):
    FakeQdrantClient.reset()
    monkeypatch.setattr("tagmemorag.storage.qdrant_vector.QdrantVectorStore._create_client", lambda *args, **kwargs: FakeQdrantClient())
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    cfg = test_config.model_copy(update={"vector_store": VectorStoreConfig(provider="qdrant", collection_prefix="test")})
    cfg.search.ann_preselect_enabled = True
    cfg.search.ann_candidate_k = 1
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    save_kb(state, cfg)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/search", json={"question": "蒸汽很小", "top_k": 2})

    assert response.status_code == 200
    assert response.json()["results"]


def test_api_search_ann_falls_back_on_qdrant_failure(monkeypatch, tmp_path, test_config, fake_embedder):
    FakeQdrantClient.reset()
    monkeypatch.setattr("tagmemorag.storage.qdrant_vector.QdrantVectorStore._create_client", lambda *args, **kwargs: FakeQdrantClient())
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    cfg = test_config.model_copy(update={"vector_store": VectorStoreConfig(provider="qdrant", collection_prefix="test")})
    cfg.search.ann_preselect_enabled = True
    cfg.search.ann_candidate_k = 2
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    save_kb(state, cfg)
    FakeQdrantClient.fail_next_search = True
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/search", json={"question": "蒸汽很小", "top_k": 2})

    assert response.status_code == 200
    assert response.json()["results"]
