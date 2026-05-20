"""Tests for build_plan reranker integration (T3 Slice 6)."""

from __future__ import annotations

import pytest

from tagmemorag.config import Settings
from tagmemorag.queryplan import build_plan


def _settings(*, enabled: bool, default_tier: str = "tier1", **overrides) -> Settings:
    s = Settings()
    s.reranker.enabled = enabled
    s.reranker.default_tier = default_tier  # type: ignore[assignment]
    for k, v in overrides.items():
        setattr(s.reranker, k, v)
    return s


# ---------- enabled flag controls everything ----------

def test_disabled_forces_tier_off_even_when_client_requests_tier1():
    s = _settings(enabled=False)
    p = build_plan("hi", "default", s, budget_spec={"rerank_tier": "tier1"})
    assert p.budget.rerank_tier == "off"
    assert p.budget.rerank_candidates_n == 0
    assert p.rerank is None


def test_enabled_with_no_client_override_uses_default_tier():
    s = _settings(enabled=True, default_tier="tier1")
    p = build_plan("hi", "default", s)
    assert p.budget.rerank_tier == "tier1"
    assert p.budget.rerank_candidates_n == 100
    assert p.rerank is not None


def test_enabled_default_tier_off_means_tier_off():
    s = _settings(enabled=True, default_tier="off")
    p = build_plan("hi", "default", s)
    assert p.budget.rerank_tier == "off"
    assert p.rerank is None


def test_client_override_when_enabled_takes_precedence():
    s = _settings(enabled=True, default_tier="tier1")
    p = build_plan("hi", "default", s, budget_spec={"rerank_tier": "tier2"})
    assert p.budget.rerank_tier == "tier2"


def test_client_can_force_off_when_enabled():
    s = _settings(enabled=True, default_tier="tier1")
    p = build_plan("hi", "default", s, budget_spec={"rerank_tier": "off"})
    assert p.budget.rerank_tier == "off"
    assert p.budget.rerank_candidates_n == 0
    assert p.rerank is None


# ---------- RerankSpec content ----------

def test_rerank_spec_uses_settings_model_id_and_version():
    s = _settings(enabled=True, model_id="Qwen/Qwen3-Reranker-0.6B", model_version="v1")
    p = build_plan("hi", "default", s)
    assert p.rerank["reranker_id"] == "qwen3-reranker-0.6b@siliconflow"
    assert p.rerank["reranker_version"] == "v1"


def test_rerank_spec_includes_instruction_when_set():
    s = _settings(enabled=True, instruction="Sort by recency")
    p = build_plan("hi", "default", s)
    assert p.rerank["instruction"] == "Sort by recency"


def test_rerank_spec_top_n_from_settings():
    s = _settings(enabled=True, top_n=50)
    p = build_plan("hi", "default", s)
    assert p.rerank["top_n"] == 50


def test_rerank_candidates_n_from_settings():
    s = _settings(enabled=True, rerank_candidates_n=200)
    p = build_plan("hi", "default", s)
    assert p.budget.rerank_candidates_n == 200


# ---------- private KB still wins over enabled ----------

def test_private_kb_forces_external_reranker_off_even_when_enabled():
    s = _settings(enabled=True)
    s.queryplan.private_kbs = ["secret"]
    p = build_plan("hi", "secret", s)
    assert p.budget.allow_external_reranker is False
    # Tier may still be tier1 (private KB doesn't force tier off, only ACL);
    # dispatcher's ACL gate handles the actual short-circuit at request time.
    assert p.persist is False


# ---------- dispatcher integration smoke ----------

def test_dispatcher_observes_settings_disabled_via_build_plan():
    """End-to-end: build_plan + dispatcher together respect enabled=False."""
    from dataclasses import dataclass
    from tagmemorag.queryplan.budget import BudgetGuard
    from tagmemorag.reranker import RerankerDispatcher

    @dataclass
    class C:
        chunk_id: str
        text: str

    s = _settings(enabled=False)
    p = build_plan("q", "default", s)
    d = RerankerDispatcher(s)
    guard = BudgetGuard(p)
    result = d.rerank(p, [C("c1", "x"), C("c2", "y")], guard)
    assert result.vendor_used == "noop"
