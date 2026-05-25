from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ...answer.base import AnswerGenerator, AnswerRequestContext
from ...answer.prompt import build_answer_prompt, validate_generation_citations
from ..state import AgentStepCtx, ToolObservation


@dataclass(frozen=True)
class FinalTool:
    generator: AnswerGenerator
    context: AnswerRequestContext | None = None
    question: str = ""
    prompt_version: str = "answer_prompt.v1"
    max_output_tokens: int = 512

    name: str = "final"
    description: str = "Generate the final answer from the prepared context."
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.input_schema is None:
            object.__setattr__(
                self,
                "input_schema",
                {"type": "object", "properties": {}, "additionalProperties": False},
            )

    def __call__(self, args: dict[str, Any], ctx: AgentStepCtx) -> ToolObservation:
        started = time.perf_counter()
        context = self.context or self._context_from_history(ctx)
        generation = self.generator.generate(context)
        generation = validate_generation_citations(
            generation,
            context.prompt.allowed_citation_ids,
        )
        return ToolObservation(
            payload={"answer": generation.to_answer_dict()},
            tokens_consumed=int(context.max_output_tokens),
            latency_ms=int((time.perf_counter() - started) * 1000),
            warnings=tuple(generation.warnings),
        )

    def _context_from_history(self, ctx: AgentStepCtx) -> AnswerRequestContext:
        retrieve_payload = _latest_retrieve_payload(ctx)
        question = self.question or _latest_query(ctx) or str(retrieve_payload.get("query") or "")
        prompt_version = str(getattr(ctx.settings.answer, "prompt_version", self.prompt_version))
        prompt = build_answer_prompt(
            question=question,
            retrieve_payload=retrieve_payload,
            prompt_version=prompt_version,
        )
        max_output_tokens = int(
            self.max_output_tokens
            or getattr(ctx.settings.answer, "max_output_tokens", 512)
        )
        return AnswerRequestContext(
            question=question,
            retrieve_payload=retrieve_payload,
            prompt=prompt,
            max_output_tokens=max_output_tokens,
        )


def _latest_retrieve_payload(ctx: AgentStepCtx) -> dict[str, Any]:
    for record in reversed(ctx.history):
        if record.tool == "retrieve":
            return record.observation.payload
    return {}


def _latest_query(ctx: AgentStepCtx) -> str:
    for record in reversed(ctx.history):
        query = str(record.args.get("query") or "").strip()
        if query:
            return query
    return ""


__all__ = ["FinalTool"]
