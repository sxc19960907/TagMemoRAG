from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any
from uuid import uuid4

from ..config import Settings
from ..types import GraphState
from .loader_splitter import LangChainAdapterUnavailable


@dataclass(frozen=True)
class TagMemoRAGRetrieverConfig:
    top_k: int | None = None
    source_k: int | None = None
    token_budget: int = 8000
    kb_name: str | None = None


class TagMemoRAGRetriever:
    """LangChain-compatible retriever facade over native TagMemoRAG retrieval."""

    def __init__(
        self,
        *,
        state: GraphState,
        settings: Settings,
        embedder: Any,
        config: TagMemoRAGRetrieverConfig | None = None,
    ) -> None:
        self.state = state
        self.settings = settings
        self.embedder = embedder
        self.config = config or TagMemoRAGRetrieverConfig()

    def invoke(self, query: str, config: Any | None = None, **kwargs: Any) -> list[Any]:
        return self.get_relevant_documents(query, **kwargs)

    def get_relevant_documents(self, query: str, **kwargs: Any) -> list[Any]:
        payload = self.retrieve(query, **kwargs)
        return retrieve_payload_to_documents(payload)

    def retrieve(self, query: str, **kwargs: Any) -> dict[str, Any]:
        from ..api import RetrieveRequest

        request = RetrieveRequest(
            question=query,
            kb_name=str(kwargs.get("kb_name") or self.config.kb_name or self.state.kb_name),
            top_k=kwargs.get("top_k", self.config.top_k),
            source_k=kwargs.get("source_k", self.config.source_k),
            token_budget=int(kwargs.get("token_budget", self.config.token_budget)),
        )
        return run_native_retrieve(
            request=request,
            state=self.state,
            settings=self.settings,
            embedder=self.embedder,
        )


def run_native_retrieve(
    *,
    request: Any,
    state: GraphState,
    settings: Settings,
    embedder: Any,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Run the native retrieve path with explicit dependencies.

    The native implementation owns QueryPlan, PlanLog, reranking, evidence, and
    context-pack behavior. The adapter temporarily installs explicit
    dependencies into the API module so it can reuse that path without copying
    the retrieval pipeline.
    """

    from .. import api

    old_settings = api.settings
    old_embedder = api.embedder
    try:
        api.settings = settings
        api.embedder = embedder
        return api._retrieve_impl(
            request,
            _AdapterRequest(trace_id=trace_id or f"langchain-{uuid4().hex}"),
            state,
            time.perf_counter(),
        )
    finally:
        api.settings = old_settings
        api.embedder = old_embedder


def retrieve_payload_to_documents(payload: dict[str, Any]) -> list[Any]:
    document_cls = _document_class()
    context_items = (payload.get("context_pack") or {}).get("items") or []
    if context_items:
        return [_document_from_context_item(document_cls, item, payload) for item in context_items if isinstance(item, dict)]
    return [_document_from_result(document_cls, item, payload) for item in payload.get("results") or [] if isinstance(item, dict)]


def _document_from_context_item(document_cls: type, item: dict[str, Any], payload: dict[str, Any]) -> Any:
    source = dict(item.get("source") or {})
    metadata = _safe_metadata(
        {
            "context_item_id": item.get("context_item_id"),
            "citation_id": item.get("citation_id"),
            "source_file": source.get("source_file"),
            "score": item.get("score"),
            "plan_id": payload.get("plan_id"),
            "build_id": payload.get("build_id"),
            "kb_name": payload.get("kb_name"),
        }
    )
    return document_cls(page_content=str(item.get("content") or ""), metadata=metadata)


def _document_from_result(document_cls: type, item: dict[str, Any], payload: dict[str, Any]) -> Any:
    metadata = _safe_metadata(
        {
            "source_file": item.get("source_file"),
            "header": item.get("header"),
            "score": item.get("score"),
            "chunk_id": item.get("chunk_id"),
            "plan_id": payload.get("plan_id"),
            "build_id": payload.get("build_id"),
            "kb_name": payload.get("kb_name"),
        }
    )
    return document_cls(page_content=str(item.get("text") or ""), metadata=metadata)


def _document_class() -> type:
    try:
        from langchain_core.documents import Document
    except ImportError as exc:
        raise LangChainAdapterUnavailable(
            "Install the optional 'langchain' extra to use LangChain retriever adapters."
        ) from exc
    return Document


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (str, int, float, bool)):
            safe[key] = value
        else:
            safe[key] = str(value)
    return safe


class _AdapterState:
    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id


class _AdapterRequest:
    def __init__(self, trace_id: str) -> None:
        self.state = _AdapterState(trace_id)


__all__ = [
    "TagMemoRAGRetriever",
    "TagMemoRAGRetrieverConfig",
    "retrieve_payload_to_documents",
    "run_native_retrieve",
]
