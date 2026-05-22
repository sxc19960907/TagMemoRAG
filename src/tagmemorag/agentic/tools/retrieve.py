from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ...retrieval import build_retrieve_response
from ...search_runtime import execute_search
from ..state import AgentStepCtx, ToolObservation


@dataclass(frozen=True)
class RetrieveTool:
    state: Any
    embedder: Any
    query_text: str
    top_k: int
    source_k: int
    trace_id: str = "agentic"
    search_id: str = "agentic-search"
    retrieve_id: str = "agentic-retrieve"

    name: str = "retrieve"
    description: str = "Retrieve evidence from the current knowledge base."
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
        started = time.perf_counter()
        query = str(args.get("query") or self.query_text)
        query_vec = self.embedder.encode_query(query)
        execution = execute_search(
            state=self.state,
            query_vec=query_vec,
            settings=ctx.settings,
            query_text=query,
            top_k=int(self.top_k),
            source_k=int(self.source_k),
            steps=int(ctx.settings.search.steps),
            decay=float(ctx.settings.search.decay),
            amplitude_cutoff=float(ctx.settings.search.amplitude_cutoff),
            aggregate=str(ctx.settings.search.aggregate),
            filters=ctx.plan.filters,
            boost_filters=None,
        )
        payload = build_retrieve_response(
            results=execution.results,
            build_id=self.state.build_id,
            kb_name=self.state.kb_name,
            trace_id=self.trace_id,
            search_id=self.search_id,
            retrieve_id=self.retrieve_id,
            token_budget=int(ctx.plan.budget.max_evidence) * 1000,
            search_time_ms=(time.perf_counter() - started) * 1000.0,
            query_text=query,
        )
        return ToolObservation(
            payload=payload,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


__all__ = ["RetrieveTool"]
