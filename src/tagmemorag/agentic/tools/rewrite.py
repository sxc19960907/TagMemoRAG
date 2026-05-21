from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..state import AgentStepCtx, ToolObservation


@dataclass(frozen=True)
class RewriteTool:
    name: str = "rewrite"
    description: str = "Rewrite a query for the next retrieval step."
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.input_schema is None:
            object.__setattr__(
                self,
                "input_schema",
                {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            )

    def __call__(self, args: dict[str, Any], ctx: AgentStepCtx) -> ToolObservation:
        query = str(args.get("query") or "")
        return ToolObservation(
            payload={
                "query": query,
                "reason": "c1_stub_identity",
            }
        )


__all__ = ["RewriteTool"]
