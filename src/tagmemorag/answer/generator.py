from __future__ import annotations

from typing import TYPE_CHECKING

from .base import AnswerCitation, AnswerGeneration, AnswerGenerator, AnswerRequestContext

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings


class NoopAnswerGenerator:
    """Deterministic local generator for default-off behavior and tests."""

    def __init__(self, *, model_id: str = "noop", model_version: str = "v1", prompt_version: str = "answer_prompt.v1"):
        self.model_id = model_id or "noop"
        self.model_version = model_version
        self.prompt_version = prompt_version

    def generate(self, context: AnswerRequestContext) -> AnswerGeneration:
        first_citation = sorted(context.prompt.allowed_citation_ids)[0] if context.prompt.allowed_citation_ids else ""
        citations = (AnswerCitation(first_citation),) if first_citation else ()
        text = "Answer generation is running in noop mode."
        return AnswerGeneration(
            text=text,
            citations=citations,
            model_id=self.model_id,
            model_version=self.model_version,
            prompt_version=self.prompt_version,
            warnings=("answer_noop_provider",),
        )


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
