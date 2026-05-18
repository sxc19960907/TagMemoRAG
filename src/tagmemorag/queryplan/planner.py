"""Rule-based QueryPlan builder (Architecture v2 § A2 / planner stage).

T2 implementation: pure function, no side effects. The plan is constructed
from the API request + Settings; persistence is the caller's job (plan_log).

Future tasks can add LLM-based planners that produce additional rewrites
or richer intent classification — they plug in by replacing classify_intent
or adding a callable hook around build_plan output. The QueryPlan dataclass
itself is stable.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from dataclasses import replace

from .intent import classify_intent
from .plan import (
    Budget,
    Intent,
    QueryPlan,
    make_deadline_at,
    new_plan_id,
    now_iso_utc,
)
from .privacy import mask_rewrites

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings


PLAN_SCHEMA_VERSION = 1
DEFAULT_STRATEGY: dict[str, Any] = {
    "indexes": ["vector", "lexical", "metadata", "graph"],
}


def _query_hash(question: str) -> str:
    return "sha256:" + hashlib.sha256(question.strip().encode("utf-8")).hexdigest()


def _resolve_budget(spec: dict | None, settings: "Settings") -> Budget:
    """Build a Budget from optional client override + Settings defaults.

    `spec` is a partial dict (BudgetSpec from API or None). Missing fields
    fall back to Settings.queryplan.default_*.
    """
    qpc = settings.queryplan
    spec = spec or {}
    return Budget(
        latency_ms=int(spec.get("latency_ms") or qpc.default_latency_ms),
        rerank_tier=str(spec.get("rerank_tier") or qpc.default_rerank_tier),
        max_evidence=int(spec.get("max_evidence") or qpc.default_max_evidence),
        allow_external_reranker=bool(
            spec["allow_external_reranker"]
            if spec.get("allow_external_reranker") is not None
            else qpc.default_allow_external_reranker
        ),
        deadline_at=0.0,  # set below
    )


def build_plan(
    question: str,
    kb_name: str,
    settings: "Settings",
    *,
    filters: dict[str, Any] | None = None,
    budget_spec: dict | None = None,
    strategy: dict[str, Any] | None = None,
) -> QueryPlan:
    """Construct a QueryPlan for a /search or /retrieve call.

    Parameters
    ----------
    question
        Raw user query string. Hashed before persistence; never stored raw.
    kb_name
        Target KB. Used for private-KB short-circuit + plan log routing.
    settings
        Active Settings. Read-only; not mutated.
    filters
        Snapshot of SearchFilters.to_filter_dict() or None.
    budget_spec
        Partial dict from BudgetSpec (API request) or None for defaults.
    strategy
        Optional override for index selection. Defaults to all-indexes.

    Side effects: NONE. Pure function. Persistence is caller's responsibility.
    """
    plan_id = new_plan_id()
    query_hash = _query_hash(question)

    budget = _resolve_budget(budget_spec, settings)
    budget = replace(budget, deadline_at=make_deadline_at(budget.latency_ms))

    intent = classify_intent(question, kb_name, settings)

    rewrites = (question,)
    masked_rewrites = mask_rewrites(rewrites, settings.queryplan.pii_mask_rules)

    persist = True
    if kb_name in settings.queryplan.private_kbs:
        # Private KB short-circuit (D8): no persistence + force local rerank.
        persist = False
        budget = replace(budget, allow_external_reranker=False)

    return QueryPlan(
        schema_version=PLAN_SCHEMA_VERSION,
        plan_id=plan_id,
        kb_name=kb_name,
        query_hash=query_hash,
        query_rewrites_masked=masked_rewrites,
        intent=intent,
        filters=dict(filters) if filters else {},
        strategy=dict(strategy) if strategy else dict(DEFAULT_STRATEGY),
        rerank=None,  # T3 fills
        budget=budget,
        created_at=now_iso_utc(),
        persist=persist,
    )


__all__ = ["build_plan", "PLAN_SCHEMA_VERSION", "DEFAULT_STRATEGY"]
