"""Tests for RerankerDispatcher (T3 Slice 5)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from tagmemorag.config import Settings
from tagmemorag.queryplan import build_plan
from tagmemorag.queryplan.budget import BudgetGuard
from tagmemorag.reranker import (
    NoopReranker,
    RerankCache,
    RerankerCircuitOpenError,
    RerankerDispatcher,
    RerankerOutcome,
    RerankerVendorError,
)


@dataclass
class _Candidate:
    chunk_id: str
    text: str


def _candidates(n: int = 3) -> list[_Candidate]:
    return [_Candidate(chunk_id=f"c{i}", text=f"text {i}") for i in range(n)]


class _FakeReranker:
    """Minimal Reranker for dispatcher tests; deterministic, controllable."""

    def __init__(
        self,
        items_to_return: list[tuple[str, float]] | None = None,
        raise_exc: Exception | None = None,
    ):
        self.id = "fake@test"
        self.version = "v1"
        self.max_seq_length = 32768
        self.supports_instruction = True
        self.calls: list[dict] = []
        self._items = items_to_return
        self._raise = raise_exc

    def rerank(self, query, docs, instruction, budget_ms):
        self.calls.append({
            "query": query,
            "docs": list(docs),
            "instruction": instruction,
            "budget_ms": budget_ms,
        })
        if self._raise is not None:
            raise self._raise
        items = (
            tuple(self._items) if self._items is not None
            else tuple((d.chunk_id, 1.0 - i * 0.1) for i, d in enumerate(docs))
        )
        return RerankerOutcome(items=items, truncated_chunk_ids=(), vendor_id=self.id)


def _enabled_settings() -> Settings:
    s = Settings()
    s.reranker.enabled = True
    return s


def _plan(s: Settings, *, kb: str = "default", question: str = "hello"):
    """Build a plan with rerank tier active for testing dispatcher routing."""
    plan = build_plan(question, kb, s)
    # Tests force tier on regardless of build_plan defaults
    return plan


def _plan_with_tier(s: Settings, tier: str, allow_external: bool = True, kb: str = "default"):
    plan = build_plan("question text", kb, s)
    new_budget = type(plan.budget)(
        latency_ms=plan.budget.latency_ms,
        rerank_tier=tier,  # type: ignore[arg-type]
        max_evidence=plan.budget.max_evidence,
        allow_external_reranker=allow_external,
        deadline_at=plan.budget.deadline_at,
    )
    return type(plan)(
        schema_version=plan.schema_version,
        plan_id=plan.plan_id,
        kb_name=plan.kb_name,
        query_hash=plan.query_hash,
        query_rewrites_masked=plan.query_rewrites_masked,
        intent=plan.intent,
        filters=plan.filters,
        strategy=plan.strategy,
        rerank=plan.rerank,
        budget=new_budget,
        created_at=plan.created_at,
        served_by_generation=plan.served_by_generation,
        served_by_build_id=plan.served_by_build_id,
        persist=plan.persist,
    )


# ---------- short-circuit branches ----------

def test_dispatcher_disabled_returns_noop():
    s = Settings()  # enabled=False default
    fake = _FakeReranker()
    d = RerankerDispatcher(s, primary=fake)
    plan = _plan_with_tier(s, "tier1")
    guard = BudgetGuard(plan)
    result = d.rerank(plan, _candidates(), guard)
    assert result.vendor_used == "noop"
    assert result.cache_status == "skipped"
    assert "noop_via_settings_disabled" in result.warnings
    assert fake.calls == []


def test_dispatcher_tier_off_returns_noop():
    s = _enabled_settings()
    fake = _FakeReranker()
    d = RerankerDispatcher(s, primary=fake)
    plan = _plan_with_tier(s, "off")
    guard = BudgetGuard(plan)
    result = d.rerank(plan, _candidates(), guard)
    assert result.vendor_used == "noop"
    assert "noop_via_tier_off" in result.warnings
    assert fake.calls == []


def test_dispatcher_acl_blocks_external():
    s = _enabled_settings()
    fake = _FakeReranker()
    d = RerankerDispatcher(s, primary=fake)
    plan = _plan_with_tier(s, "tier1", allow_external=False)
    guard = BudgetGuard(plan)
    result = d.rerank(plan, _candidates(), guard)
    assert result.vendor_used == "noop"
    assert "noop_via_acl" in result.warnings
    assert fake.calls == []


def test_dispatcher_budget_too_tight_skips():
    s = _enabled_settings()
    s.reranker.min_budget_ms = 10000  # huge requirement
    fake = _FakeReranker()
    d = RerankerDispatcher(s, primary=fake)
    plan = _plan_with_tier(s, "tier1")
    guard = BudgetGuard(plan)
    result = d.rerank(plan, _candidates(), guard)
    assert result.vendor_used == "noop"
    assert "reranker_skipped_due_to_budget" in result.warnings
    assert fake.calls == []


# ---------- happy path ----------

def test_dispatcher_calls_vendor_and_calibrates():
    s = _enabled_settings()
    fake = _FakeReranker(items_to_return=[("c1", 5.0), ("c0", 2.0), ("c2", 1.0)])
    d = RerankerDispatcher(s, primary=fake)
    plan = _plan_with_tier(s, "tier1")
    guard = BudgetGuard(plan)
    result = d.rerank(plan, _candidates(3), guard)

    assert result.vendor_used == "fake@test"
    assert result.cache_status == "miss"
    assert len(fake.calls) == 1
    # min-max calibration: 5→1.0, 2→0.25, 1→0.0; sorted desc by calibrated
    chunk_order = [it.chunk_id for it in result.items]
    assert chunk_order == ["c1", "c0", "c2"]
    assert result.items[0].calibrated_score == 1.0
    assert result.items[-1].calibrated_score == 0.0


def test_dispatcher_uses_runtime_query_text_without_storing_raw_query():
    s = _enabled_settings()
    fake = _FakeReranker()
    d = RerankerDispatcher(s, primary=fake)
    plan = _plan_with_tier(s, "tier1")
    guard = BudgetGuard(plan)

    d.rerank(plan, _candidates(), guard, query_text="E21 washer cannot drain")

    assert fake.calls[0]["query"] == "E21 washer cannot drain"
    assert not hasattr(plan, "query_text")
    assert "E21 washer cannot drain" not in plan.to_basic_dict()["query_hash"]


def test_dispatcher_passes_instruction_from_plan():
    s = _enabled_settings()
    fake = _FakeReranker()
    d = RerankerDispatcher(s, primary=fake)
    plan = _plan_with_tier(s, "tier1")
    # T3: rerank lives as a dict on plan.rerank (not a RerankSpec dataclass).
    new_rerank = {
        "reranker_id": "fake@test",
        "reranker_version": "v1",
        "instruction": "Sort by recency",
        "top_n": 10,
    }
    plan = type(plan)(
        schema_version=plan.schema_version,
        plan_id=plan.plan_id,
        kb_name=plan.kb_name,
        query_hash=plan.query_hash,
        query_rewrites_masked=plan.query_rewrites_masked,
        intent=plan.intent,
        filters=plan.filters,
        strategy=plan.strategy,
        rerank=new_rerank,
        budget=plan.budget,
        created_at=plan.created_at,
        served_by_generation=plan.served_by_generation,
        served_by_build_id=plan.served_by_build_id,
        persist=plan.persist,
    )
    guard = BudgetGuard(plan)
    d.rerank(plan, _candidates(), guard)
    assert fake.calls[0]["instruction"] == "Sort by recency"


# ---------- cache ----------

def test_dispatcher_cache_hit_skips_vendor():
    s = _enabled_settings()
    fake = _FakeReranker()
    cache = RerankCache(max_entries=10)
    d = RerankerDispatcher(s, primary=fake, cache=cache)
    plan = _plan_with_tier(s, "tier1")
    guard = BudgetGuard(plan)

    r1 = d.rerank(plan, _candidates(), guard)
    assert r1.cache_status == "miss"
    assert len(fake.calls) == 1

    r2 = d.rerank(plan, _candidates(), guard)
    assert r2.cache_status == "hit"
    assert len(fake.calls) == 1  # no second call


def test_dispatcher_cache_miss_writes_to_cache():
    s = _enabled_settings()
    fake = _FakeReranker()
    cache = RerankCache(max_entries=10)
    d = RerankerDispatcher(s, primary=fake, cache=cache)
    plan = _plan_with_tier(s, "tier1")
    guard = BudgetGuard(plan)
    d.rerank(plan, _candidates(), guard)
    assert cache.size() == 1


def test_dispatcher_cache_disabled_uses_no_cache():
    s = _enabled_settings()
    s.reranker.cache_enabled = False
    fake = _FakeReranker()
    d = RerankerDispatcher(s, primary=fake)
    plan = _plan_with_tier(s, "tier1")
    guard = BudgetGuard(plan)
    d.rerank(plan, _candidates(), guard)
    d.rerank(plan, _candidates(), guard)
    assert len(fake.calls) == 2  # both miss


# ---------- failure paths ----------

def test_dispatcher_vendor_error_falls_back_to_noop():
    s = _enabled_settings()
    fake = _FakeReranker(raise_exc=RerankerVendorError("down"))
    d = RerankerDispatcher(s, primary=fake)
    plan = _plan_with_tier(s, "tier1")
    guard = BudgetGuard(plan)
    result = d.rerank(plan, _candidates(), guard)
    assert result.vendor_used == "noop"
    assert any("RerankerVendorError" in w for w in result.warnings)


def test_dispatcher_circuit_open_falls_back():
    s = _enabled_settings()
    fake = _FakeReranker(raise_exc=RerankerCircuitOpenError("open"))
    d = RerankerDispatcher(s, primary=fake)
    plan = _plan_with_tier(s, "tier1")
    guard = BudgetGuard(plan)
    result = d.rerank(plan, _candidates(), guard)
    assert result.vendor_used == "noop"
    assert any("RerankerCircuitOpenError" in w for w in result.warnings)


def test_dispatcher_unexpected_exception_falls_back():
    s = _enabled_settings()
    fake = _FakeReranker(raise_exc=RuntimeError("oops"))
    d = RerankerDispatcher(s, primary=fake)
    plan = _plan_with_tier(s, "tier1")
    guard = BudgetGuard(plan)
    result = d.rerank(plan, _candidates(), guard)
    assert result.vendor_used == "noop"
    assert any("unexpected_RuntimeError" in w for w in result.warnings)


# ---------- ordering ----------

def test_dispatcher_sorts_results_descending_by_calibrated_score():
    s = _enabled_settings()
    fake = _FakeReranker(items_to_return=[("c0", 0.1), ("c1", 0.9), ("c2", 0.5)])
    d = RerankerDispatcher(s, primary=fake)
    plan = _plan_with_tier(s, "tier1")
    guard = BudgetGuard(plan)
    result = d.rerank(plan, _candidates(3), guard)
    chunk_ids = [it.chunk_id for it in result.items]
    assert chunk_ids == ["c1", "c2", "c0"]
