from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .state import AgentState
from .tools.registry import AgentToolRegistry


@dataclass(frozen=True)
class ToolDecision:
    tool: str
    args: dict[str, Any]
    rationale: str = ""


class DecisionGenerator(Protocol):
    def choose_tool(self, state: AgentState, registry: AgentToolRegistry) -> ToolDecision | None:
        ...


class RuleOnlyDecisionGenerator:
    def choose_tool(self, state: AgentState, registry: AgentToolRegistry) -> ToolDecision | None:
        return None


class OpenAICompatibleDecisionGenerator:
    def choose_tool(self, state: AgentState, registry: AgentToolRegistry) -> ToolDecision | None:
        raise NotImplementedError("OpenAI-compatible decision generation is owned by a later agentic child task")


__all__ = [
    "DecisionGenerator",
    "OpenAICompatibleDecisionGenerator",
    "RuleOnlyDecisionGenerator",
    "ToolDecision",
]
