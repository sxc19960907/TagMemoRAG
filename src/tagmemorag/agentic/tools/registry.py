from __future__ import annotations

from .base import AgentTool


class AgentToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        name = str(tool.name or "").strip()
        if not name:
            raise ValueError("agent tool name is required")
        if name in self._tools:
            raise ValueError(f"agent tool already registered: {name}")
        self._tools[name] = tool

    def get(self, name: str) -> AgentTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"agent tool not registered: {name}") from exc

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def openai_schemas(self) -> list[dict]:
        schemas = []
        for tool in self._tools.values():
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": dict(tool.input_schema),
                    },
                }
            )
        return schemas


__all__ = ["AgentToolRegistry"]
