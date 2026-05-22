from __future__ import annotations

from typing import Any

from ..agentic.tools import AgentToolRegistry
from .loader_splitter import LangChainAdapterUnavailable


def registry_to_langchain_tools(registry: AgentToolRegistry, ctx: Any) -> list[Any]:
    """Wrap AgentToolRegistry entries as LangChain StructuredTool objects."""

    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:
        raise LangChainAdapterUnavailable(
            "Install the optional 'langchain' extra to use LangChain tool adapters."
        ) from exc

    wrapped = []
    for name in registry.names():
        tool = registry.get(name)

        def _run(payload: dict[str, Any] | None = None, *, _tool=tool, **kwargs: Any) -> dict[str, Any]:
            args = dict(payload or {})
            args.update(kwargs)
            observation = _tool(args, ctx)
            return observation.to_dict()

        wrapped.append(
            StructuredTool.from_function(
                func=_run,
                name=tool.name,
                description=tool.description,
                args_schema=None,
            )
        )
    return wrapped


__all__ = ["registry_to_langchain_tools"]
