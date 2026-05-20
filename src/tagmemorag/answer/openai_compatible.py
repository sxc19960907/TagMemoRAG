from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

import httpx

from ..errors import InvalidConfigError
from .base import AnswerCitation, AnswerGeneration, AnswerGenerationError, AnswerRequestContext

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings


class OpenAICompatibleAnswerGenerator:
    """OpenAI-compatible chat completions answer generator."""

    def __init__(self, settings: "Settings", *, http_client: httpx.Client | None = None):
        self.settings = settings
        self._http = http_client

    def generate(self, context: AnswerRequestContext) -> AnswerGeneration:
        cfg = self.settings.answer
        api_key = os.environ.get(cfg.api_key_env)
        if not api_key:
            raise InvalidConfigError(
                f"Answer API key environment variable is not set: {cfg.api_key_env}",
                {"api_key_env": cfg.api_key_env, "provider": cfg.provider},
            )
        payload = {
            "model": cfg.model_id,
            "messages": list(context.prompt.messages),
            "temperature": float(cfg.temperature),
            "max_tokens": min(int(context.max_output_tokens), int(cfg.max_output_tokens)),
        }
        try:
            response = self._client().post(
                _chat_url(cfg.base_url, cfg.chat_completions_url),
                json=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=httpx.Timeout(float(cfg.timeout_seconds)),
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            raise AnswerGenerationError(f"answer generation failed: {type(exc).__name__}") from exc
        return _parse_chat_completion(data, model_id=cfg.model_id, model_version=cfg.model_version, prompt_version=cfg.prompt_version)

    def _client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=httpx.Timeout(float(self.settings.answer.timeout_seconds)))
        return self._http


def _chat_url(base_url: str, override: str | None) -> str:
    if override:
        return override
    return base_url.rstrip("/") + "/chat/completions"


def _parse_chat_completion(data: dict[str, Any], *, model_id: str, model_version: str, prompt_version: str) -> AnswerGeneration:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AnswerGenerationError("answer generation response missing choices")
    message = dict(choices[0].get("message") or {})
    content = message.get("content")
    if isinstance(content, list):
        text = "\n".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
    else:
        text = str(content or "")
    citations = []
    raw_citations = message.get("citations") or data.get("citations") or []
    if isinstance(raw_citations, list):
        for item in raw_citations:
            if isinstance(item, dict):
                cid = str(item.get("citation_id") or "")
            else:
                cid = str(item or "")
            if cid:
                citations.append(AnswerCitation(cid))
    return AnswerGeneration(
        text=text,
        citations=tuple(citations),
        model_id=model_id,
        model_version=model_version,
        prompt_version=prompt_version,
    )


__all__ = ["OpenAICompatibleAnswerGenerator"]
