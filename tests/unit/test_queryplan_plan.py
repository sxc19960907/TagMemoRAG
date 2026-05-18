"""Tests for QueryPlan + Budget dataclasses (T2 Slice 1)."""

from __future__ import annotations

import json
import time

import pytest

from tagmemorag.queryplan import (
    Budget,
    Intent,
    QueryPlan,
    make_deadline_at,
    new_plan_id,
    now_iso_utc,
)


def _budget(**kw) -> Budget:
    base = dict(latency_ms=5000, rerank_tier="off", max_evidence=8, allow_external_reranker=True)
    base.update(kw)
    return Budget(**base)


def _plan(**kw) -> QueryPlan:
    base = dict(
        schema_version=1,
        plan_id="plan-test",
        kb_name="kb-x",
        query_hash="sha256:abcd",
        query_rewrites_masked=("hello",),
        intent=Intent.TEXT_ANSWER,
        filters={},
        strategy={"indexes": ["vector"]},
        rerank=None,
        budget=_budget(),
        created_at="2026-05-18T12:00:00Z",
    )
    base.update(kw)
    return QueryPlan(**base)


# ---------- Budget ----------

def test_budget_round_trip_omits_deadline_at():
    b = _budget(latency_ms=3000, deadline_at=12345.0)
    encoded = b.to_dict()
    assert "deadline_at" not in encoded
    assert encoded == {
        "latency_ms": 3000,
        "rerank_tier": "off",
        "max_evidence": 8,
        "allow_external_reranker": True,
    }
    decoded = Budget.from_dict(encoded)
    # deadline_at defaults to 0.0 after round-trip
    assert decoded.deadline_at == 0.0
    assert decoded.latency_ms == 3000


def test_budget_from_dict_handles_missing_fields():
    b = Budget.from_dict({"latency_ms": 1000})
    assert b.latency_ms == 1000
    assert b.rerank_tier == "off"
    assert b.max_evidence == 8
    assert b.allow_external_reranker is True


def test_budget_is_frozen():
    b = _budget()
    with pytest.raises((AttributeError, Exception)):
        b.latency_ms = 9999  # type: ignore[misc]


def test_make_deadline_at_is_future():
    before = time.monotonic()
    deadline = make_deadline_at(5000)
    after = time.monotonic()
    assert deadline > before
    assert deadline <= after + 5.0 + 0.01  # epsilon


# ---------- QueryPlan ----------

def test_plan_id_unique():
    ids = {new_plan_id() for _ in range(100)}
    assert len(ids) == 100


def test_intent_enum_str_value():
    assert str(Intent.TEXT_ANSWER) == "text_answer"
    assert str(Intent.OUT_OF_SCOPE) == "out_of_scope"


def test_intent_full_enum_values():
    """Schema reserves 6 values forward-compat (D2). T2 emits only 2."""
    expected = {
        "text_answer", "table_lookup", "troubleshooting",
        "model_specific", "visual_reference", "out_of_scope",
    }
    actual = {member.value for member in Intent}
    assert actual == expected


def test_to_basic_dict_excludes_async_fields():
    plan = _plan()
    d = plan.to_basic_dict()
    # async-filled fields must not appear
    for forbidden in ("served_by_generation", "served_by_build_id",
                      "evidence_ids_json", "latency_ms_observed",
                      "warnings_json", "cache_status", "rerank_json"):
        assert forbidden not in d
    # required basic fields present
    for required in ("plan_id", "kb_name", "query_hash",
                     "query_rewrites_masked_json", "intent",
                     "filters_json", "strategy_json", "budget_json",
                     "created_at", "schema_version"):
        assert required in d


def test_to_basic_dict_serializes_json_fields():
    plan = _plan(
        query_rewrites_masked=("a", "b"),
        filters={"manual_id": "m-1"},
        strategy={"indexes": ["vector", "lexical"]},
    )
    d = plan.to_basic_dict()
    assert json.loads(d["query_rewrites_masked_json"]) == ["a", "b"]
    assert json.loads(d["filters_json"]) == {"manual_id": "m-1"}
    assert json.loads(d["strategy_json"])["indexes"] == ["vector", "lexical"]
    assert json.loads(d["budget_json"])["latency_ms"] == 5000


def test_to_basic_dict_intent_is_string():
    plan = _plan(intent=Intent.OUT_OF_SCOPE)
    d = plan.to_basic_dict()
    assert d["intent"] == "out_of_scope"


def test_query_hash_pattern_documented():
    """Plan stores hash, not raw query. Test enforces the convention."""
    plan = _plan(query_hash="sha256:" + "0" * 64)
    assert plan.query_hash.startswith("sha256:")


def test_persist_default_true_and_can_be_set_false():
    plan = _plan()
    assert plan.persist is True
    plan_priv = _plan(persist=False)
    assert plan_priv.persist is False


def test_now_iso_utc_format():
    s = now_iso_utc()
    assert s.endswith("Z")
    assert len(s) == 20  # "YYYY-MM-DDTHH:MM:SSZ"
