"""Tests for BudgetSpec on SearchRequest / RetrieveRequest (T2 Slice 4)."""

from __future__ import annotations

import pytest

from tagmemorag.api import BudgetSpec, RetrieveRequest, SearchRequest
from tagmemorag.config import Settings
from tagmemorag.queryplan import build_plan


def test_search_request_default_budget_is_none():
    r = SearchRequest(question="hi")
    assert r.budget is None


def test_search_request_accepts_full_budget_spec():
    r = SearchRequest(
        question="hi",
        budget=BudgetSpec(
            latency_ms=2000,
            rerank_tier="tier1",
            max_evidence=5,
            allow_external_reranker=False,
        ),
    )
    d = r.budget.to_planner_dict()
    assert d == {
        "latency_ms": 2000,
        "rerank_tier": "tier1",
        "max_evidence": 5,
        "allow_external_reranker": False,
    }


def test_search_request_accepts_partial_budget():
    r = SearchRequest(question="hi", budget=BudgetSpec(latency_ms=1000))
    d = r.budget.to_planner_dict()
    assert d == {"latency_ms": 1000}


def test_search_request_json_parse_with_budget():
    r = SearchRequest.model_validate({"question": "hi", "budget": {"latency_ms": 800}})
    assert r.budget is not None
    assert r.budget.latency_ms == 800


def test_budget_spec_rejects_zero_latency():
    with pytest.raises(Exception):  # pydantic ValidationError
        BudgetSpec(latency_ms=0)


def test_budget_spec_rejects_zero_max_evidence():
    with pytest.raises(Exception):
        BudgetSpec(max_evidence=0)


def test_budget_spec_invalid_rerank_tier_rejected():
    with pytest.raises(Exception):
        BudgetSpec(rerank_tier="custom")


def test_retrieve_request_inherits_budget_field():
    r = RetrieveRequest(question="hi", budget=BudgetSpec(latency_ms=500))
    assert r.budget is not None
    assert r.budget.latency_ms == 500


def test_budget_spec_to_planner_dict_omits_none():
    spec = BudgetSpec(latency_ms=1000, max_evidence=None, rerank_tier=None)
    d = spec.to_planner_dict()
    assert "latency_ms" in d
    assert "max_evidence" not in d
    assert "rerank_tier" not in d


def test_budget_spec_passes_through_build_plan():
    """Integration: BudgetSpec → planner dict → build_plan applies override.

    Note (T3 D6): rerank_tier is governed by Settings.reranker.enabled. With
    reranker disabled (default), build_plan forces tier=off regardless of
    client request. This test enables reranker explicitly to verify the
    BudgetSpec wire-through.
    """
    s = Settings()
    s.reranker.enabled = True
    spec = BudgetSpec(latency_ms=1500, rerank_tier="tier1")
    plan = build_plan("hi", "default", s, budget_spec=spec.to_planner_dict())
    assert plan.budget.latency_ms == 1500
    assert plan.budget.rerank_tier == "tier1"
    # max_evidence falls through to settings default
    assert plan.budget.max_evidence == s.queryplan.default_max_evidence


def test_search_request_omitted_budget_uses_settings_defaults_via_build_plan():
    s = Settings()
    r = SearchRequest(question="hi")
    spec_dict = r.budget.to_planner_dict() if r.budget else None
    plan = build_plan("hi", "default", s, budget_spec=spec_dict)
    assert plan.budget.latency_ms == s.queryplan.default_latency_ms


def test_allow_external_reranker_false_explicit_passes_through():
    """Pydantic falsy bool must not be confused with None."""
    spec = BudgetSpec(allow_external_reranker=False)
    d = spec.to_planner_dict()
    assert d == {"allow_external_reranker": False}

    s = Settings()
    plan = build_plan("hi", "default", s, budget_spec=d)
    assert plan.budget.allow_external_reranker is False
