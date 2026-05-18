"""Reranker first-class component (Architecture v2 § A3 / T3)."""

from .base import (
    RerankDoc,
    RerankResult,
    RerankResultItem,
    RerankSpec,
    Reranker,
    RerankerOutcome,
)
from .local_fallback import NoopReranker

__all__ = [
    "NoopReranker",
    "RerankDoc",
    "RerankResult",
    "RerankResultItem",
    "RerankSpec",
    "Reranker",
    "RerankerOutcome",
]
