"""QueryPlan + Budget dataclasses (Architecture v2 § A2).

This module is the cross-cutting contract between API entry and the retrieval
pipeline. A `QueryPlan` is constructed once per /search or /retrieve call and
threaded through every downstream component so that:

- Components can read filters, intent, budget, strategy without re-parsing the
  request body.
- The plan can be persisted (privacy-masked) for later replay (T5).
- Budget enforces request-level early exit via deadline_at.

Reranker and rerank ID are deliberately NOT part of plan_id: per Architecture
v2 § A1, changing the reranker must not invalidate persisted artifacts.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class Intent(StrEnum):
    """Query intent enum.

    T2 ships only TEXT_ANSWER + OUT_OF_SCOPE. The other four are reserved
    for forward compatibility (T6 / answer endpoint, Phase 7B visual).
    """

    TEXT_ANSWER = "text_answer"
    TABLE_LOOKUP = "table_lookup"
    TROUBLESHOOTING = "troubleshooting"
    MODEL_SPECIFIC = "model_specific"
    VISUAL_REFERENCE = "visual_reference"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass(frozen=True)
class Budget:
    """Request-level resource budget.

    `deadline_at` is monotonic-clock-relative (`time.monotonic()`) and is
    NOT serialized — it's only meaningful within a single process. JSON
    consumers reconstruct Budget without it.
    """

    latency_ms: int
    rerank_tier: str = "off"  # "off" | "tier1" | "tier2"
    max_evidence: int = 8
    allow_external_reranker: bool = True
    deadline_at: float = 0.0  # set by build_plan; not serialized

    def to_dict(self) -> dict[str, Any]:
        return {
            "latency_ms": self.latency_ms,
            "rerank_tier": self.rerank_tier,
            "max_evidence": self.max_evidence,
            "allow_external_reranker": self.allow_external_reranker,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Budget":
        return cls(
            latency_ms=int(data.get("latency_ms") or 0),
            rerank_tier=str(data.get("rerank_tier") or "off"),
            max_evidence=int(data.get("max_evidence") or 8),
            allow_external_reranker=bool(data.get("allow_external_reranker", True)),
        )


@dataclass(frozen=True, eq=False)
class QueryPlan:
    """Per-request plan; constructed once, threaded through retrieval pipeline.

    Frozen + eq=False because Settings/dict fields aren't hashable. Identity
    is plan_id; equality is intentionally object identity.
    """

    schema_version: int
    plan_id: str
    kb_name: str
    query_hash: str  # sha256 of normalized query; raw query NEVER stored
    query_rewrites_masked: tuple[str, ...]  # PII-masked rewrites
    intent: Intent
    filters: dict[str, Any]  # snapshot of SearchFilters.to_filter_dict()
    strategy: dict[str, Any]  # which indexes participate
    rerank: dict[str, Any] | None  # None until T3
    budget: Budget
    created_at: str  # ISO-8601 UTC
    served_by_generation: int | None = None  # filled async
    served_by_build_id: str = ""  # filled async
    persist: bool = True  # set False for private KBs; not serialized

    def to_basic_dict(self) -> dict[str, Any]:
        """Fields written by sync insert_basic (before response returns).

        Excludes: served_by_*, evidence_ids, latency_ms_observed, warnings,
        cache_status, rerank — those are filled async.
        """
        import json

        return {
            "plan_id": self.plan_id,
            "schema_version": self.schema_version,
            "kb_name": self.kb_name,
            "query_hash": self.query_hash,
            "query_rewrites_masked_json": json.dumps(list(self.query_rewrites_masked), ensure_ascii=False),
            "intent": str(self.intent),
            "filters_json": json.dumps(self.filters, ensure_ascii=False, sort_keys=True),
            "strategy_json": json.dumps(self.strategy, ensure_ascii=False, sort_keys=True),
            "budget_json": json.dumps(self.budget.to_dict(), ensure_ascii=False, sort_keys=True),
            "created_at": self.created_at,
        }


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_plan_id() -> str:
    return str(uuid.uuid4())


def make_deadline_at(latency_ms: int) -> float:
    return time.monotonic() + latency_ms / 1000.0


__all__ = [
    "Budget",
    "Intent",
    "QueryPlan",
    "make_deadline_at",
    "new_plan_id",
    "now_iso_utc",
]
