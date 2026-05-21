from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from tagmemorag.agentic import AgentStepCtx, ToolObservation
from tagmemorag.agentic.tools import AgentToolRegistry


@dataclass(frozen=True)
class DummyTool:
    name: str = "dummy"
    description: str = "Dummy tool"
    input_schema: dict[str, Any] | None = None

    def __post_init__(self):
        if self.input_schema is None:
            object.__setattr__(self, "input_schema", {"type": "object", "properties": {}})

    def __call__(self, args: dict[str, Any], ctx: AgentStepCtx) -> ToolObservation:
        return ToolObservation({"args": args})


def test_registry_register_get_has_names():
    registry = AgentToolRegistry()
    tool = DummyTool()

    registry.register(tool)

    assert registry.has("dummy") is True
    assert registry.get("dummy") is tool
    assert registry.names() == ("dummy",)


def test_registry_rejects_duplicate_and_missing_names():
    registry = AgentToolRegistry()
    registry.register(DummyTool())

    with pytest.raises(ValueError):
        registry.register(DummyTool())
    with pytest.raises(ValueError):
        registry.register(DummyTool(name=""))


def test_registry_openai_schemas():
    registry = AgentToolRegistry()
    registry.register(DummyTool())

    assert registry.openai_schemas() == [
        {
            "type": "function",
            "function": {
                "name": "dummy",
                "description": "Dummy tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
