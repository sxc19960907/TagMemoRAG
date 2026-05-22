from __future__ import annotations

from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.answer.base import AnswerGenerationError
from tagmemorag.config import AnswerConfig, SearchConfig, Settings, StorageConfig
from tagmemorag.state import AppState, build_kb


def _client_with_docs(tmp_path, fake_embedder, *, answer: AnswerConfig | None = None) -> tuple[TestClient, object]:
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
        search=SearchConfig(metadata_narrowing_enabled=False),
        answer=answer or AnswerConfig(),
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    api._ANSWER_GENERATOR_CACHE.clear()
    return TestClient(api.app), state


def test_answer_disabled_returns_error_and_retrieve_payload(tmp_path, fake_embedder):
    client, state = _client_with_docs(tmp_path, fake_embedder)

    response = client.post("/answer", json={"question": "蒸汽很小", "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "answer.v1"
    assert body["build_id"] == state.build_id
    assert body["answer"]["kind"] == "error"
    assert body["answer"]["refusal_reason"] == "generation_disabled"
    assert body["answer"]["citations"] == []
    assert "answer_generation_disabled" in body["warnings"]
    assert body["retrieve"]["schema_version"] == "retrieve.v1"
    assert body["retrieve"]["answerability"]["answerable"] is True


def test_answer_refuses_when_retrieve_has_no_evidence(tmp_path, fake_embedder, monkeypatch):
    client, _state = _client_with_docs(
        tmp_path,
        fake_embedder,
        answer=AnswerConfig(enabled=True, provider="noop"),
    )

    def _unexpected_generator():
        raise AssertionError("answer generator should not run for unanswerable retrieval")

    monkeypatch.setattr(api, "_answer_generator", _unexpected_generator)

    response = client.post("/answer", json={"question": "蒸汽", "filters": {"manual_id": "missing"}})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]["kind"] == "refusal"
    assert body["answer"]["refusal_reason"] == "no_results"
    assert body["answer"]["missing_evidence_hints"] == ["no_results"]
    assert body["retrieve"]["evidence"] == []
    assert "answer_refused:no_results" in body["warnings"]


def test_answer_noop_provider_returns_cited_answer(tmp_path, fake_embedder):
    client, _state = _client_with_docs(
        tmp_path,
        fake_embedder,
        answer=AnswerConfig(enabled=True, provider="noop"),
    )

    response = client.post("/answer", json={"question": "蒸汽很小", "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    answer = body["answer"]
    assert answer["kind"] == "answer"
    assert answer["text"] == "Answer generation is running in noop mode."
    assert answer["model_id"] == "noop"
    assert answer["prompt_version"] == "answer_prompt.v1"
    assert answer["citations"] == [{"citation_id": body["retrieve"]["citations"][0]["citation_id"]}]
    assert "answer_noop_provider" in body["warnings"]


def test_answer_provider_failure_stays_in_answer_payload(tmp_path, fake_embedder, monkeypatch):
    client, _state = _client_with_docs(
        tmp_path,
        fake_embedder,
        answer=AnswerConfig(enabled=True, provider="noop"),
    )

    class FailingGenerator:
        def generate(self, context):
            raise AnswerGenerationError("provider unavailable")

    monkeypatch.setattr(api, "_answer_generator", lambda: FailingGenerator())

    response = client.post("/answer", json={"question": "蒸汽很小", "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]["kind"] == "error"
    assert body["answer"]["refusal_reason"] == "generation_failed"
    assert "answer_generation_failed:AnswerGenerationError" in body["warnings"]
    assert body["retrieve"]["evidence"]


def test_answer_can_omit_retrieve_payload(tmp_path, fake_embedder):
    client, _state = _client_with_docs(
        tmp_path,
        fake_embedder,
        answer=AnswerConfig(enabled=True, provider="noop"),
    )

    response = client.post("/answer", json={"question": "蒸汽很小", "top_k": 1, "include_retrieve": False})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]["kind"] == "answer"
    assert "retrieve" not in body


def test_answer_request_accepts_agentic_surface(tmp_path, fake_embedder):
    client, _state = _client_with_docs(
        tmp_path,
        fake_embedder,
        answer=AnswerConfig(enabled=True, provider="noop"),
    )

    response = client.post(
        "/answer",
        json={
            "question": "蒸汽很小",
            "top_k": 1,
            "mode": "agentic",
            "agentic": {"max_iterations": 0, "max_agent_tokens": 128, "max_tool_calls": 2},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]["kind"] == "answer"
    assert body["retrieve"]["plan_id"]


def test_qa_answer_routes_single_accessible_kb(tmp_path, fake_embedder):
    client, state = _client_with_docs(
        tmp_path,
        fake_embedder,
        answer=AnswerConfig(enabled=True, provider="noop"),
    )

    response = client.post("/qa/answer", json={"question": "蒸汽很小"})

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == {"kind": "answered", "kb_name": "default", "reason": "single_kb"}
    assert body["answer"]["kind"] == "answer"
    assert body["retrieve"]["kb_name"] == state.kb_name


def test_qa_answer_clarifies_ambiguous_multi_kb(tmp_path, fake_embedder):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
        search=SearchConfig(metadata_narrowing_enabled=False),
        answer=AnswerConfig(enabled=True, provider="noop"),
    )
    docs_a = tmp_path / "docs-a"
    docs_b = tmp_path / "docs-b"
    docs_a.mkdir()
    docs_b.mkdir()
    (docs_a / "manual.md").write_text("# CM1\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    (docs_b / "manual.md").write_text("# TX2\n清洗功能需要定期维护。\n", encoding="utf-8")
    state_a = build_kb(docs_a, "coffee", cfg, embedder=fake_embedder)
    state_b = build_kb(docs_b, "washer", cfg, embedder=fake_embedder)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState()
    api.app_state.swap_kb("coffee", state_a)
    api.app_state.swap_kb("washer", state_b)
    api._ANSWER_GENERATOR_CACHE.clear()
    client = TestClient(api.app)

    response = client.post("/qa/answer", json={"question": "这个怎么处理？"})

    assert response.status_code == 200
    body = response.json()
    assert body["route"]["kind"] == "clarification"
    assert {candidate["kb_name"] for candidate in body["route"]["candidates"]} == {"coffee", "washer"}
    assert body["answer"]["kind"] == "clarification"


def test_qa_answer_routes_multi_kb_when_question_mentions_context(tmp_path, fake_embedder):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
        search=SearchConfig(metadata_narrowing_enabled=False),
        answer=AnswerConfig(enabled=True, provider="noop"),
    )
    docs_a = tmp_path / "docs-a"
    docs_b = tmp_path / "docs-b"
    docs_a.mkdir()
    docs_b.mkdir()
    (docs_a / "manual.md").write_text("# CM1\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    (docs_b / "manual.md").write_text("# TX2\n清洗功能需要定期维护。\n", encoding="utf-8")
    state_a = build_kb(docs_a, "coffee", cfg, embedder=fake_embedder)
    state_b = build_kb(docs_b, "washer", cfg, embedder=fake_embedder)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState()
    api.app_state.swap_kb("coffee", state_a)
    api.app_state.swap_kb("washer", state_b)
    api._ANSWER_GENERATOR_CACHE.clear()
    client = TestClient(api.app)

    response = client.post("/qa/answer", json={"question": "CM1 蒸汽很小怎么办？"})

    assert response.status_code == 200
    body = response.json()
    assert body["route"]["kind"] == "answered"
    assert body["route"]["kb_name"] == "coffee"
    assert body["route"]["reason"] == "lexical_route"
