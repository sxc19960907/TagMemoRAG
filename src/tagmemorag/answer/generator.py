from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .base import AnswerCitation, AnswerGeneration, AnswerGenerator, AnswerRequestContext

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings


class NoopAnswerGenerator:
    """Deterministic local extractive generator for offline demos and tests."""

    def __init__(self, *, model_id: str = "noop", model_version: str = "v1", prompt_version: str = "answer_prompt.v1"):
        self.model_id = model_id or "noop"
        self.model_version = model_version
        self.prompt_version = prompt_version

    def generate(self, context: AnswerRequestContext) -> AnswerGeneration:
        citation_id, excerpt = _first_supported_excerpt(context)
        citations = (AnswerCitation(citation_id),) if citation_id else ()
        text = f"{excerpt} [{citation_id}]" if citation_id and excerpt else _insufficient_evidence_text()
        return AnswerGeneration(
            text=text,
            citations=citations,
            model_id=self.model_id,
            model_version=self.model_version,
            prompt_version=self.prompt_version,
            warnings=("answer_noop_provider",),
        )


def _first_supported_excerpt(context: AnswerRequestContext) -> tuple[str, str]:
    allowed = set(context.prompt.allowed_citation_ids)
    for item in (context.retrieve_payload.get("context_pack") or {}).get("items") or []:
        citation_id = str(item.get("citation_id") or "")
        content = _clean_excerpt(str(item.get("content") or ""))
        if citation_id in allowed and content:
            return citation_id, content
    for item in context.retrieve_payload.get("evidence") or []:
        citation_id = str(item.get("citation_id") or "")
        text = _clean_excerpt(str(item.get("text") or ""))
        if citation_id in allowed and text:
            return citation_id, text
    return "", ""


def _clean_excerpt(text: str, *, max_chars: int = 480) -> str:
    cleaned = _drop_repeated_heading(text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    clipped = cleaned[:max_chars].rstrip()
    for mark in (". ", "; ", "! ", "? "):
        pos = clipped.rfind(mark)
        if pos >= max_chars // 3:
            return clipped[: pos + 1].strip()
    return clipped.rstrip(" ,;:")


def _drop_repeated_heading(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) >= 2 and lines[1].startswith(lines[0]):
        return "\n".join(lines[1:])
    return text


def _insufficient_evidence_text() -> str:
    return "The available evidence is insufficient to produce an extractive answer."


def create_answer_generator(settings: "Settings") -> AnswerGenerator:
    cfg = settings.answer
    if cfg.provider == "noop":
        return NoopAnswerGenerator(
            model_id=cfg.model_id or "noop",
            model_version=cfg.model_version,
            prompt_version=cfg.prompt_version,
        )
    if cfg.provider == "openai_compatible":
        from .openai_compatible import OpenAICompatibleAnswerGenerator

        return OpenAICompatibleAnswerGenerator(settings)
    raise ValueError(f"Unsupported answer provider: {cfg.provider}")


__all__ = ["NoopAnswerGenerator", "create_answer_generator"]
