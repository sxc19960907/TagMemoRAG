from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..state import AgentStepCtx, ToolObservation


@runtime_checkable
class AgentTool(Protocol):
    name: str
    description: str
    input_schema: dict[str, Any]

    def __call__(self, args: dict[str, Any], ctx: AgentStepCtx) -> ToolObservation:
        ...


__all__ = ["AgentTool", "AgentStepCtx", "ToolObservation"]
