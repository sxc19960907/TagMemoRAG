"""Tests for queryplan/intent / privacy / budget / planner (T2 Slice 2)."""

from __future__ import annotations

import time
from dataclasses import replace

import pytest

from tagmemorag.config import Settings
from tagmemorag.queryplan import (
    Budget,
    BudgetGuard,
    DEFAULT_OUT_OF_SCOPE_KEYWORDS,
    Intent,
    QueryPlan,
    build_plan,
    classify_intent,
    make_deadline_at,
    mask_rewrites,
)


# ---------- intent classifier ----------

def test_classify_default_keywords_match():
    s = Settings()
    assert classify_intent("今天天气怎么样", "default", s) == Intent.OUT_OF_SCOPE
    assert classify_intent("what time is it now", "default", s) == Intent.OUT_OF_SCOPE


def test_classify_default_text_answer():
    s = Settings()
    assert classify_intent("how do I clean the filter", "default", s) == Intent.TEXT_ANSWER
    assert classify_intent("蒸汽功能怎么用", "default", s) == Intent.TEXT_ANSWER


def test_classify_settings_override_keywords():
    s = Settings()
    s.queryplan.out_of_scope_keywords = ["specific_word"]
    assert classify_intent("contains specific_word", "default", s) == Intent.OUT_OF_SCOPE
    assert classify_intent("今天天气", "default", s) == Intent.TEXT_ANSWER  # default list overridden


def test_classify_empty_keyword_list_falls_through():
    s = Settings()
    s.queryplan.out_of_scope_keywords = []
    assert classify_intent("anything at all", "default", s) == Intent.TEXT_ANSWER


def test_default_keyword_list_is_non_empty():
    assert len(DEFAULT_OUT_OF_SCOPE_KEYWORDS) > 0


# ---------- privacy mask ----------

def test_mask_passthrough_when_no_rules():
    out = mask_rewrites(["a", "b"], None)
    assert out == ("a", "b")


def test_mask_applies_single_rule():
    rules = [{"pattern": r"\d{11}", "replace": "[PHONE]"}]
    out = mask_rewrites(["call 13800138000 now"], rules)
    assert out == ("call [PHONE] now",)


def test_mask_applies_multiple_rules_in_order():
    rules = [
        {"pattern": r"\d{11}", "replace": "###PHONE###"},
        {"pattern": r"[a-z]{3}@[a-z]{3}", "replace": "###EMAIL###"},
    ]
    out = mask_rewrites(["call 13800138000 mail abc@xyz"], rules)
    assert out == ("call ###PHONE### mail ###EMAIL###",)


def test_mask_empty_rules_passthrough():
    out = mask_rewrites(["x"], [])
    assert out == ("x",)


def test_mask_invalid_regex_skipped_silently():
    rules = [{"pattern": "[", "replace": "X"}]  # invalid regex
    out = mask_rewrites(["abc"], rules)
    assert out == ("abc",)


def test_mask_returns_tuple_for_immutability():
    out = mask_rewrites(["a"], None)
    assert isinstance(out, tuple)


# ---------- BudgetGuard ----------

def test_budget_guard_remaining_when_deadline_unset():
    plan = QueryPlan(
        schema_version=1, plan_id="p", kb_name="k", query_hash="h",
        query_rewrites_masked=("q",), intent=Intent.TEXT_ANSWER,
        filters={}, strategy={}, rerank=None,
        budget=Budget(latency_ms=3000, deadline_at=0.0),
        created_at="x",
    )
    guard = BudgetGuard(plan)
    # deadline_at unset → returns full budget
    assert guard.remaining_ms() == 3000
    assert not guard.exhausted()


def test_budget_guard_exhausted_when_past_deadline():
    plan = QueryPlan(
        schema_version=1, plan_id="p", kb_name="k", query_hash="h",
        query_rewrites_masked=("q",), intent=Intent.TEXT_ANSWER,
        filters={}, strategy={}, rerank=None,
        budget=Budget(latency_ms=1, deadline_at=time.monotonic() - 1.0),
        created_at="x",
    )
    guard = BudgetGuard(plan)
    assert guard.remaining_ms() == 0
    assert guard.exhausted()


def test_budget_guard_remaining_decreases_over_time():
    deadline = make_deadline_at(50)  # 50ms from now
    plan = QueryPlan(
        schema_version=1, plan_id="p", kb_name="k", query_hash="h",
        query_rewrites_masked=("q",), intent=Intent.TEXT_ANSWER,
        filters={}, strategy={}, rerank=None,
        budget=Budget(latency_ms=50, deadline_at=deadline),
        created_at="x",
    )
    guard = BudgetGuard(plan)
    first = guard.remaining_ms()
    time.sleep(0.06)
    second = guard.remaining_ms()
    assert first > second
    assert second == 0


# ---------- build_plan ----------

def test_build_plan_returns_complete_plan():
    s = Settings()
    plan = build_plan("clean filter", "default", s)
    assert plan.kb_name == "default"
    assert plan.intent == Intent.TEXT_ANSWER
    assert plan.query_hash.startswith("sha256:")
    assert plan.query_rewrites_masked == ("clean filter",)  # passthrough
    assert plan.budget.latency_ms == 5000
    assert plan.budget.deadline_at > time.monotonic()
    assert plan.persist is True
    assert plan.rerank is None  # T3 fills
    assert "vector" in plan.strategy["indexes"]


def test_build_plan_unique_plan_id():
    s = Settings()
    ids = {build_plan("q", "default", s).plan_id for _ in range(50)}
    assert len(ids) == 50


def test_build_plan_does_not_store_raw_query():
    s = Settings()
    sensitive = "my secret query 13800138000"
    plan = build_plan(sensitive, "default", s)
    # query_hash is derived from query, but does NOT contain it verbatim
    assert sensitive not in plan.query_hash
    # rewrites are passthrough in T2 (no rules), so they DO contain the query.
    # That's intentional for now; mask hook addresses real PII later.
    assert plan.query_rewrites_masked[0] == sensitive


def test_build_plan_with_pii_mask_rules_applies_mask():
    s = Settings()
    s.queryplan.pii_mask_rules = [{"pattern": r"\d{11}", "replace": "[PHONE]"}]
    plan = build_plan("call 13800138000", "default", s)
    assert plan.query_rewrites_masked == ("call [PHONE]",)


def test_build_plan_out_of_scope_intent():
    s = Settings()
    plan = build_plan("今天天气如何", "default", s)
    assert plan.intent == Intent.OUT_OF_SCOPE


def test_build_plan_private_kb_short_circuit():
    s = Settings()
    s.queryplan.private_kbs = ["secret_kb"]
    plan = build_plan("anything", "secret_kb", s)
    assert plan.persist is False
    assert plan.budget.allow_external_reranker is False


def test_build_plan_non_private_kb_persists():
    s = Settings()
    s.queryplan.private_kbs = ["secret_kb"]
    plan = build_plan("anything", "default", s)
    assert plan.persist is True
    assert plan.budget.allow_external_reranker is True


def test_build_plan_budget_spec_override():
    s = Settings()
    plan = build_plan("q", "default", s, budget_spec={"latency_ms": 1000})
    assert plan.budget.latency_ms == 1000


def test_build_plan_partial_budget_spec_falls_through():
    s = Settings()
    plan = build_plan("q", "default", s, budget_spec={"max_evidence": 12})
    assert plan.budget.max_evidence == 12
    assert plan.budget.latency_ms == 5000  # falls through to default


def test_build_plan_filters_snapshot():
    s = Settings()
    filters_in = {"manual_id": "m1", "tags": ["t1"]}
    plan = build_plan("q", "default", s, filters=filters_in)
    assert plan.filters == filters_in
    # snapshot, not reference
    filters_in["manual_id"] = "MUTATED"
    assert plan.filters["manual_id"] == "m1"


def test_build_plan_strategy_default():
    s = Settings()
    plan = build_plan("q", "default", s)
    assert plan.strategy["indexes"] == ["vector", "lexical", "metadata", "graph"]


def test_build_plan_strategy_override():
    s = Settings()
    plan = build_plan("q", "default", s, strategy={"indexes": ["vector"]})
    assert plan.strategy["indexes"] == ["vector"]


def test_build_plan_no_side_effects_on_settings():
    s = Settings()
    s.queryplan.private_kbs = ["secret_kb"]
    initial_private = list(s.queryplan.private_kbs)
    build_plan("q", "secret_kb", s)
    # Settings should be untouched after build_plan
    assert s.queryplan.private_kbs == initial_private
    assert s.queryplan.default_allow_external_reranker is True
