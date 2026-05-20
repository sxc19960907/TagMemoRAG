from __future__ import annotations

import httpx
import pytest

from tagmemorag.answer.base import AnswerRequestContext
from tagmemorag.answer.generator import NoopAnswerGenerator, create_answer_generator
from tagmemorag.answer.openai_compatible import OpenAICompatibleAnswerGenerator
from tagmemorag.answer.prompt import build_answer_prompt
from tagmemorag.config import AnswerConfig, Settings
from tagmemorag.errors import InvalidConfigError


def _context() -> AnswerRequestContext:
    prompt = build_answer_prompt(
        question="q",
        retrieve_payload={"citations": [{"citation_id": "cit_001"}], "context_pack": {"items": []}},
        prompt_version="answer_prompt.v1",
    )
    return AnswerRequestContext(question="q", retrieve_payload={}, prompt=prompt, max_output_tokens=64)


def test_noop_answer_generator_is_deterministic():
    generation = NoopAnswerGenerator().generate(_context())

    assert generation.text
    assert [c.citation_id for c in generation.citations] == ["cit_001"]
    assert "answer_noop_provider" in generation.warnings


def test_create_answer_generator_noop():
    gen = create_answer_generator(Settings())

    assert isinstance(gen, NoopAnswerGenerator)


def test_openai_compatible_requires_api_key(monkeypatch):
    cfg = Settings(answer=AnswerConfig(provider="openai_compatible", model_id="m", api_key_env="MISSING_ANSWER_KEY"))
    monkeypatch.delenv("MISSING_ANSWER_KEY", raising=False)

    with pytest.raises(InvalidConfigError):
        OpenAICompatibleAnswerGenerator(cfg).generate(_context())


def test_openai_compatible_chat_completion(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        payload = request.read()
        seen["body"] = payload.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "Use the steam wand. [cit_001]",
                            "citations": [{"citation_id": "cit_001"}],
                        }
                    }
                ]
            },
        )

    monkeypatch.setenv("ANSWER_KEY", "secret")
    cfg = Settings(
        answer=AnswerConfig(
            provider="openai_compatible",
            model_id="chat-model",
            api_key_env="ANSWER_KEY",
            base_url="https://example.test/v1",
        )
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))

    generation = OpenAICompatibleAnswerGenerator(cfg, http_client=client).generate(_context())

    assert seen["url"] == "https://example.test/v1/chat/completions"
    assert seen["auth"] == "Bearer secret"
    assert "chat-model" in seen["body"]
    assert generation.text == "Use the steam wand. [cit_001]"
    assert [c.citation_id for c in generation.citations] == ["cit_001"]
