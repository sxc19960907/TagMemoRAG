from __future__ import annotations

from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.state import AppState, build_kb


def test_health_always_ok(test_config, fake_embedder):
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState()
    client = TestClient(api.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.text == "ok"


def test_ready_503_when_embedder_not_ready(test_config, fake_embedder):
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState()
    client = TestClient(api.app)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.text == "embedder not ready"
    assert response.headers["content-type"].startswith("text/plain")


def test_ready_503_when_kb_not_loaded(test_config, fake_embedder):
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState()
    api.app_state.mark_embedder_ready()
    client = TestClient(api.app)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.text == "kb not loaded"


def test_ready_503_when_shutting_down(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    api.app_state.mark_embedder_ready()
    api.app_state.begin_shutdown()
    client = TestClient(api.app)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.text == "shutting down"


def test_ready_200_when_all_ready(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    api.app_state.mark_embedder_ready()
    client = TestClient(api.app)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.text == "ok"
