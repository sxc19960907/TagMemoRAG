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
    retrieve_payload = {
        "citations": [{"citation_id": "cit_001"}, {"citation_id": "cit_002"}, {"citation_id": "cit_003"}],
        "context_pack": {
            "items": [
                {
                    "citation_id": "cit_001",
                    "content": "Weak steam\n\nWeak steam is usually caused by a blocked nozzle.\nClean the nozzle and check the water tank.",
                },
                {
                    "citation_id": "cit_002",
                    "content": "Nozzle care\n\nClean the steam nozzle after each use because a clogged nozzle can reduce steam output.",
                },
                {
                    "citation_id": "cit_003",
                    "content": "Power setup\n\nUse a grounded outlet before first startup.",
                },
            ]
        },
    }
    prompt = build_answer_prompt(
        question="weak steam nozzle",
        retrieve_payload=retrieve_payload,
        prompt_version="answer_prompt.v1",
    )
    return AnswerRequestContext(question="weak steam nozzle", retrieve_payload=retrieve_payload, prompt=prompt, max_output_tokens=64)


def test_noop_answer_generator_is_deterministic():
    generation = NoopAnswerGenerator().generate(_context())

    assert generation.text == (
        "建议先这样处理：\n"
        "1. Weak steam is usually caused by a blocked nozzle. Clean the nozzle and check the water tank. [cit_001]\n"
        "2. Clean the steam nozzle after each use because a clogged nozzle can reduce steam output. [cit_002]"
    )
    assert [c.citation_id for c in generation.citations] == ["cit_001", "cit_002"]
    assert "answer_noop_provider" in generation.warnings


def test_noop_answer_generator_deduplicates_supported_excerpts():
    retrieve_payload = {
        "citations": [{"citation_id": "cit_001"}, {"citation_id": "cit_002"}],
        "context_pack": {
            "items": [
                {"citation_id": "cit_001", "content": "Filter\n\nClean the filter weekly."},
                {"citation_id": "cit_002", "content": "Filter\n\nClean the filter weekly."},
            ]
        },
    }
    prompt = build_answer_prompt(question="filter clean", retrieve_payload=retrieve_payload, prompt_version="answer_prompt.v1")
    context = AnswerRequestContext(question="filter clean", retrieve_payload=retrieve_payload, prompt=prompt, max_output_tokens=64)

    generation = NoopAnswerGenerator().generate(context)

    assert generation.text == "Clean the filter weekly. [cit_001]"
    assert [c.citation_id for c in generation.citations] == ["cit_001"]


def test_noop_answer_generator_falls_back_to_first_supported_excerpt():
    retrieve_payload = {
        "citations": [{"citation_id": "cit_001"}],
        "context_pack": {"items": [{"citation_id": "cit_001", "content": "Power setup\n\nUse a grounded outlet."}]},
    }
    prompt = build_answer_prompt(question="unrelated topic", retrieve_payload=retrieve_payload, prompt_version="answer_prompt.v1")
    context = AnswerRequestContext(question="unrelated topic", retrieve_payload=retrieve_payload, prompt=prompt, max_output_tokens=64)

    generation = NoopAnswerGenerator().generate(context)

    assert generation.text == "Use a grounded outlet. [cit_001]"
    assert [c.citation_id for c in generation.citations] == ["cit_001"]


def test_noop_answer_generator_handles_no_supported_evidence():
    retrieve_payload = {
        "citations": [{"citation_id": "cit_001"}],
        "context_pack": {"items": [{"citation_id": "cit_fake", "content": "Unsupported text"}]},
    }
    prompt = build_answer_prompt(question="q", retrieve_payload=retrieve_payload, prompt_version="answer_prompt.v1")
    context = AnswerRequestContext(question="q", retrieve_payload=retrieve_payload, prompt=prompt, max_output_tokens=64)

    generation = NoopAnswerGenerator().generate(context)

    assert generation.text == "The available evidence is insufficient to produce an extractive answer."
    assert generation.citations == ()


def test_noop_answer_generator_formats_chinese_troubleshooting_steps():
    retrieve_payload = {
        "citations": [{"citation_id": "cit_001"}, {"citation_id": "cit_002"}, {"citation_id": "cit_003"}],
        "context_pack": {
            "items": [
                {"citation_id": "cit_001", "content": "蒸汽很小\n\n蒸汽很小时，先清洗蒸汽喷嘴。"},
                {"citation_id": "cit_002", "content": "水箱\n\n请确认水箱已经加水并安装到位。"},
                {"citation_id": "cit_003", "content": "预热\n\n机器需要完成预热后再使用蒸汽。"},
            ]
        },
    }
    prompt = build_answer_prompt(question="蒸汽很小怎么办", retrieve_payload=retrieve_payload, prompt_version="answer_prompt.v1")
    context = AnswerRequestContext(question="蒸汽很小怎么办", retrieve_payload=retrieve_payload, prompt=prompt, max_output_tokens=64)

    generation = NoopAnswerGenerator().generate(context)

    assert generation.text == (
        "建议先这样处理：\n"
        "1. 蒸汽很小时，先清洗蒸汽喷嘴。 [cit_001]\n"
        "2. 请确认水箱已经加水并安装到位。 [cit_002]\n"
        "3. 机器需要完成预热后再使用蒸汽。 [cit_003]"
    )
    assert [c.citation_id for c in generation.citations] == ["cit_001", "cit_002", "cit_003"]


def test_noop_answer_generator_prioritizes_manual_safety_guidance():
    retrieve_payload = {
        "citations": [{"citation_id": "cit_001"}, {"citation_id": "cit_002"}],
        "context_pack": {
            "items": [
                {"citation_id": "cit_001", "content": "故障安全\n\n如果出现异味、漏电或持续高温，请立即断电并联系售后。"},
                {"citation_id": "cit_002", "content": "日常清洁\n\n每次使用后擦拭外壳。"},
            ]
        },
    }
    prompt = build_answer_prompt(question="机器有异味和持续高温怎么办", retrieve_payload=retrieve_payload, prompt_version="answer_prompt.v1")
    context = AnswerRequestContext(
        question="机器有异味和持续高温怎么办",
        retrieve_payload=retrieve_payload,
        prompt=prompt,
        max_output_tokens=64,
    )

    generation = NoopAnswerGenerator().generate(context)

    assert generation.text == "建议先保证安全：\n1. 如果出现异味、漏电或持续高温，请立即断电并联系售后。 [cit_001]"
    assert [c.citation_id for c in generation.citations] == ["cit_001"]


def test_noop_answer_generator_refuses_unsupported_part_number_claim():
    retrieve_payload = {
        "citations": [{"citation_id": "cit_001"}],
        "context_pack": {
            "items": [
                {"citation_id": "cit_001", "content": "维修说明\n\n本说明书没有列出蒸汽泵配件编号，请联系授权售后。"}
            ]
        },
    }
    prompt = build_answer_prompt(question="蒸汽泵配件编号是多少", retrieve_payload=retrieve_payload, prompt_version="answer_prompt.v1")
    context = AnswerRequestContext(
        question="蒸汽泵配件编号是多少",
        retrieve_payload=retrieve_payload,
        prompt=prompt,
        max_output_tokens=64,
    )

    generation = NoopAnswerGenerator().generate(context)

    assert generation.text == (
        "现有说明书证据不足，无法确认需要这样处理。 "
        "可确认的信息是：本说明书没有列出蒸汽泵配件编号，请联系授权售后。 [cit_001]"
    )
    assert [c.citation_id for c in generation.citations] == ["cit_001"]


def test_noop_answer_generator_does_not_fabricate_replacement_instruction():
    retrieve_payload = {
        "citations": [{"citation_id": "cit_001"}, {"citation_id": "cit_002"}],
        "context_pack": {
            "items": [
                {"citation_id": "cit_001", "content": "蒸汽很小\n\n蒸汽很小时，清洗喷嘴并确认水箱有水。"},
                {"citation_id": "cit_002", "content": "预热\n\n蒸汽输出前需要等待机器完成预热。"},
            ]
        },
    }
    prompt = build_answer_prompt(question="蒸汽很小是不是要直接换泵", retrieve_payload=retrieve_payload, prompt_version="answer_prompt.v1")
    context = AnswerRequestContext(
        question="蒸汽很小是不是要直接换泵",
        retrieve_payload=retrieve_payload,
        prompt=prompt,
        max_output_tokens=64,
    )

    generation = NoopAnswerGenerator().generate(context)

    assert generation.text == (
        "现有说明书证据不足，无法确认需要这样处理。\n"
        "1. 可确认的信息：蒸汽很小时，清洗喷嘴并确认水箱有水。 [cit_001]\n"
        "2. 可确认的信息：蒸汽输出前需要等待机器完成预热。 [cit_002]"
    )
    assert "必须" not in generation.text
    assert "直接换泵" not in generation.text
    assert [c.citation_id for c in generation.citations] == ["cit_001", "cit_002"]


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


def test_openai_compatible_extracts_text_citations(monkeypatch):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "Check the drain hose [cit_001]. Then clean the filter [cit_002]. Unknown [cit_fake].",
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

    assert [c.citation_id for c in generation.citations] == ["cit_001", "cit_002", "cit_fake"]


def test_openai_compatible_rejects_empty_content(monkeypatch):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

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

    with pytest.raises(Exception) as exc:
        OpenAICompatibleAnswerGenerator(cfg, http_client=client).generate(_context())

    assert "missing content" in str(exc.value)
