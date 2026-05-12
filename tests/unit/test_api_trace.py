from __future__ import annotations

from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.state import AppState, build_kb


def _client_with_state(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    api.app_state.mark_embedder_ready()
    return TestClient(api.app)


def test_trace_id_generated_when_header_absent(tmp_path, test_config, fake_embedder):
    client = _client_with_state(tmp_path, test_config, fake_embedder)

    response = client.post("/search", json={"question": "蒸汽"})

    assert response.status_code == 200
    assert response.headers["X-Trace-Id"]
    assert response.json()["trace_id"] == response.headers["X-Trace-Id"]


def test_trace_id_respected_when_header_present(tmp_path, test_config, fake_embedder):
    client = _client_with_state(tmp_path, test_config, fake_embedder)

    response = client.post("/search", json={"question": "蒸汽"}, headers={"X-Trace-Id": "trace-fixed"})

    assert response.status_code == 200
    assert response.headers["X-Trace-Id"] == "trace-fixed"
    assert response.json()["trace_id"] == "trace-fixed"
