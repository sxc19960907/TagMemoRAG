from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...answer.base import AnswerGenerator
from ..tools.final import FinalTool
from ..tools.grade import GradeTool
from ..tools.registry import AgentToolRegistry
from ..tools.retrieve import RetrieveTool
from ..tools.rewrite import RewriteTool


@dataclass(frozen=True)
class ProductionAgentToolsConfig:
    top_k: int
    source_k: int
    trace_id: str = "agentic"
    search_id: str = "agentic-search"
    retrieve_id: str = "agentic-retrieve"
    answer_max_output_tokens: int = 512


def build_production_agent_tool_registry(
    *,
    state: Any,
    embedder: Any,
    answer_generator: AnswerGenerator,
    reranker_dispatcher: Any,
    query_text: str,
    config: ProductionAgentToolsConfig,
) -> AgentToolRegistry:
    registry = AgentToolRegistry()
    registry.register(
        RetrieveTool(
            state=state,
            embedder=embedder,
            query_text=query_text,
            top_k=config.top_k,
            source_k=config.source_k,
            trace_id=config.trace_id,
            search_id=config.search_id,
            retrieve_id=config.retrieve_id,
        )
    )
    registry.register(GradeTool(reranker_dispatcher, candidates=[], query_text=query_text))
    registry.register(RewriteTool())
    registry.register(
        FinalTool(
            answer_generator,
            context=None,
            question=query_text,
            max_output_tokens=config.answer_max_output_tokens,
        )
    )
    return registry


__all__ = [
    "ProductionAgentToolsConfig",
    "build_production_agent_tool_registry",
]
