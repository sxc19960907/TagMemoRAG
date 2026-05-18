"""Reranker first-class component (Architecture v2 § A3).

Vendor-neutral interface + dataclasses. Concrete implementations (SF Qwen3,
Noop) live in sibling modules. Dispatcher routes between them per Budget +
Settings flags.

reranker_id and reranker_version intentionally do NOT enter the persistent
ID system (chunk_id / vector_point_id). Reranking is a read-side scoring
pass; swapping the reranker must NEVER invalidate stored vectors or chunks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol


@dataclass(frozen=True)
class RerankDoc:
    """Input doc to a rerank call. Adapter is responsible for truncation."""

    chunk_id: str
    text: str


@dataclass(frozen=True)
class RerankResultItem:
    chunk_id: str
    raw_score: float
    calibrated_score: float


@dataclass(frozen=True)
class RerankResult:
    """Outcome of a single rerank call.

    `vendor_used` distinguishes "qwen3-reranker-0.6b@siliconflow" / "noop" /
    other adapters so plan log readers can attribute outcomes.

    `cache_status` is "miss" when the dispatcher actually called the vendor,
    "hit" when served from RerankCache, "skipped" when budget/ACL/policy
    short-circuited.
    """

    items: tuple[RerankResultItem, ...]
    truncated_chunk_ids: tuple[str, ...]
    vendor_used: str
    cache_status: Literal["miss", "hit", "skipped"]
    latency_ms: int
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "items": [
                {
                    "chunk_id": it.chunk_id,
                    "raw_score": it.raw_score,
                    "calibrated_score": it.calibrated_score,
                }
                for it in self.items
            ],
            "truncated_chunk_ids": list(self.truncated_chunk_ids),
            "vendor_used": self.vendor_used,
            "cache_status": self.cache_status,
            "latency_ms": self.latency_ms,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class RerankSpec:
    """Stored on QueryPlan.rerank when the request is rerank-eligible.

    Fields chosen to match plan_log.rerank_json schema; build_plan attaches
    when Budget.rerank_tier != "off".
    """

    reranker_id: str
    reranker_version: str
    instruction: str | None
    top_n: int

    def to_dict(self) -> dict:
        return {
            "reranker_id": self.reranker_id,
            "reranker_version": self.reranker_version,
            "instruction": self.instruction,
            "top_n": self.top_n,
        }


class Reranker(Protocol):
    """Vendor-neutral rerank interface.

    Every adapter (SF Qwen3, BGE/BCE, NoopReranker, future local cross-encoder)
    implements this. Dispatcher calls .rerank() with a budget_ms; adapter is
    responsible for translating that to its transport-level timeout.

    .rerank() returns a partial result-shaped object — the dispatcher fills
    cache_status and calibrated_score after the adapter returns. To keep the
    Protocol simple, adapters return a dict-like with "items" (raw scores)
    and "truncated_chunk_ids"; the dispatcher constructs the final RerankResult.
    """

    id: str
    version: str
    max_seq_length: int
    supports_instruction: bool

    def rerank(
        self,
        query: str,
        docs: list[RerankDoc],
        instruction: str | None,
        budget_ms: int,
    ) -> "RerankerOutcome": ...


@dataclass(frozen=True)
class RerankerOutcome:
    """Adapter-level return: raw scores + truncation; calibration happens later.

    Items are returned in arbitrary order (typically vendor's response order);
    dispatcher sorts by calibrated_score after calibration.
    """

    items: tuple[tuple[str, float], ...]  # (chunk_id, raw_score)
    truncated_chunk_ids: tuple[str, ...] = ()
    vendor_id: str = ""
