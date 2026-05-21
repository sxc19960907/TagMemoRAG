from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ...answer.base import AnswerGenerator, AnswerRequestContext
from ..state import AgentStepCtx, ToolObservation


@dataclass(frozen=True)
class FinalTool:
    generator: AnswerGenerator
    context: AnswerRequestContext

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
        generation = self.generator.generate(self.context)
        return ToolObservation(
            payload={"answer": generation.to_answer_dict()},
            tokens_consumed=int(self.context.max_output_tokens),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


__all__ = ["FinalTool"]
