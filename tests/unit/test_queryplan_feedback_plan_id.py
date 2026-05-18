"""Tests for SearchFeedback plan_id field (T2 Slice 6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tagmemorag.config import Settings, StorageConfig
from tagmemorag.retrieval_feedback import (
    SearchFeedback,
    feedback_from_payload,
)


def _payload(**overrides) -> dict:
    base = {
        "feedback_id": "fb-1",
        "kb_name": "default",
        "trace_id": "t",
        "search_id": "s",
        "retrieve_id": "",
        "build_id": "b",
        "query": "hello",
        "outcome": "helpful",
        "created_at": "2026-05-18T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_search_feedback_default_plan_id_empty():
    fb = SearchFeedback(
        feedback_id="x", kb_name="kb", trace_id="t", search_id="s",
        retrieve_id="", build_id="b", query="q",
        outcome="helpful", created_at="2026-05-18T00:00:00Z",
    )
    assert fb.plan_id == ""


def test_to_dict_includes_plan_id():
    fb = SearchFeedback(
        feedback_id="x", kb_name="kb", trace_id="t", search_id="s",
        retrieve_id="", build_id="b", query="q",
        outcome="helpful", created_at="2026-05-18T00:00:00Z",
        plan_id="plan-42",
    )
    d = fb.to_dict()
    assert d["plan_id"] == "plan-42"


def test_from_payload_with_plan_id():
    fb = feedback_from_payload("default", _payload(plan_id="plan-99"))
    assert fb.plan_id == "plan-99"


def test_from_payload_without_plan_id_defaults_empty():
    """Backward compat: legacy rows without plan_id parse as empty string."""
    fb = feedback_from_payload("default", _payload())
    assert fb.plan_id == ""


def test_jsonl_round_trip_with_plan_id(tmp_path: Path):
    """Simulate writing a feedback row to jsonl and reading it back."""
    fb = SearchFeedback(
        feedback_id="x", kb_name="kb", trace_id="t", search_id="s",
        retrieve_id="", build_id="b", query="q",
        outcome="helpful", created_at="2026-05-18T00:00:00Z",
        plan_id="plan-1",
    )
    path = tmp_path / "feedback.jsonl"
    path.write_text(json.dumps(fb.to_dict(), ensure_ascii=False) + "\n", encoding="utf-8")

    line = path.read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    assert parsed["plan_id"] == "plan-1"

    fb2 = feedback_from_payload("kb", parsed)
    assert fb2.plan_id == "plan-1"


def test_legacy_jsonl_without_plan_id_parses(tmp_path: Path):
    """jsonl predating T2 has no plan_id column; must still parse."""
    legacy_row = _payload()
    legacy_row.pop("plan_id", None)
    fb = feedback_from_payload("default", legacy_row)
    assert fb.plan_id == ""
    # to_dict round-trip emits plan_id="" so future readers see consistent shape
    redumped = fb.to_dict()
    assert redumped["plan_id"] == ""


def test_plan_id_too_long_rejected():
    """plan_id length bounded (matches build_id / search_id pattern); over-bound raises."""
    from tagmemorag.errors import ServiceError

    long_id = "x" * 200  # over the 120 char bound
    with pytest.raises(ServiceError):
        feedback_from_payload("default", _payload(plan_id=long_id))
