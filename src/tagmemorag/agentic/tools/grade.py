from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ..grader import CragGradeThresholds, grade_rerank_result
from ..state import AgentStepCtx, GradeOutcome, ToolObservation


@dataclass(frozen=True)
class GradeTool:
    dispatcher: Any
    candidates: list[Any]
    query_text: str = ""
    thresholds: CragGradeThresholds = CragGradeThresholds()

    name: str = "grade"
    description: str = "Grade retrieved evidence using the configured reranker signal."
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
        rerank_result = self.dispatcher.rerank(
            ctx.plan,
            self.candidates,
            ctx.guard,
            query_text=str(args.get("query") or self.query_text),
        )
        grade = grade_rerank_result(rerank_result, self.thresholds)
        return ToolObservation(
            payload={"grade": grade.to_dict(), "rerank": rerank_result.to_dict()},
            latency_ms=int((time.perf_counter() - started) * 1000),
            warnings=tuple(rerank_result.warnings),
            rerank_result=rerank_result,
        )


__all__ = ["GradeTool"]
