from __future__ import annotations

import json

import pytest

from tagmemorag.config import Settings, StorageConfig
from tagmemorag.errors import ServiceError
from tagmemorag.retrieval_feedback import (
    create_feedback,
    export_eval_promotion,
    feedback_log_path,
    list_feedback,
    preview_eval_promotion,
    review_feedback,
)


def _settings(tmp_path) -> Settings:
    return Settings(storage=StorageConfig(data_dir=str(tmp_path / "data")), model={"dim": 64})


def _payload(**overrides):
    data = {
        "trace_id": "trace-1",
        "search_id": "search-1",
        "retrieve_id": "retrieve-1",
        "build_id": "build-1",
        "query": "E05 蒸汽异常怎么处理",
        "outcome": "missing_result",
        "selected_results": [{"rank": 1, "node_id": 2, "source_file": "coffee.md", "header": "蒸汽", "manual_id": "cm1"}],
        "selected_evidence_ids": ["ev_001"],
        "selected_context_item_ids": ["ctx_001"],
        "answerable": False,
        "failure_reason": "missing_expected_fault_code",
        "expected": [{"source_file": "coffee.md", "header": "E05", "text_contains": ["清洗喷嘴"], "metadata": {"manual_id": "cm1"}}],
        "note": "Expected the E05 troubleshooting section.",
    }
    data.update(overrides)
    return data


def test_feedback_append_list_and_review_overlay(tmp_path):
    cfg = _settings(tmp_path)

    feedback = create_feedback("default", _payload(feedback_id="fb-1"), cfg)
    assert feedback.feedback_id == "fb-1"
    assert feedback_log_path("default", cfg).exists()

    rows = list_feedback("default", cfg, status="new", outcome="missing_result")
    assert [row.feedback_id for row in rows] == ["fb-1"]
    assert rows[0].expected[0].metadata == {"manual_id": "cm1"}
    assert rows[0].retrieve_id == "retrieve-1"
    assert rows[0].selected_evidence_ids == ("ev_001",)
    assert rows[0].selected_context_item_ids == ("ctx_001",)
    assert rows[0].answerable is False
    assert rows[0].failure_reason == "missing_expected_fault_code"

    reviewed = review_feedback("default", "fb-1", cfg, status="triaged", operator_note="Good eval candidate.")
    assert reviewed.status == "triaged"
    assert reviewed.operator_note == "Good eval candidate."
    assert list_feedback("default", cfg, status="new") == []
    assert list_feedback("default", cfg, status="triaged")[0].operator_note == "Good eval candidate."


def test_feedback_validation_rejects_unsafe_and_oversized_payloads(tmp_path):
    cfg = _settings(tmp_path)

    with pytest.raises(ServiceError) as invalid_kb:
        create_feedback("../default", _payload(), cfg)
    assert invalid_kb.value.code == "INVALID_INPUT"

    with pytest.raises(ServiceError) as invalid_source:
        create_feedback("default", _payload(expected=[{"source_file": "../secret.md"}]), cfg)
    assert invalid_source.value.code == "INVALID_INPUT"

    with pytest.raises(ServiceError) as invalid_note:
        create_feedback("default", _payload(note="x" * 2001), cfg)
    assert invalid_note.value.code == "INVALID_INPUT"


def test_promotion_preview_builds_eval_case_and_skips_unusable_feedback(tmp_path):
    cfg = _settings(tmp_path)
    good = create_feedback("default", _payload(feedback_id="fb-good"), cfg)
    bad = create_feedback("default", _payload(feedback_id="fb-bad", expected=[], selected_results=[], outcome="wrong_manual"), cfg)

    preview = preview_eval_promotion("default", [good.feedback_id, bad.feedback_id], cfg)

    assert [case["id"] for case in preview.cases] == ["feedback-fb-good"]
    assert preview.cases[0]["query"] == "E05 蒸汽异常怎么处理"
    assert preview.cases[0]["relevant"][0]["metadata"] == {"manual_id": "cm1"}
    assert preview.skipped == ({"feedback_id": "fb-bad", "reason": "no_usable_relevant_matcher"},)


def test_export_eval_promotion_requires_explicit_existing_file_mode_and_marks_promoted(tmp_path):
    cfg = _settings(tmp_path)
    feedback = create_feedback("default", _payload(feedback_id="fb-1"), cfg)
    output = tmp_path / "eval_drafts" / "default" / "feedback.jsonl"

    preview = export_eval_promotion("default", [feedback.feedback_id], cfg, output_path=str(output))
    assert preview.cases
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["id"] == "feedback-fb-1"
    assert list_feedback("default", cfg, status="promoted")[0].feedback_id == "fb-1"

    with pytest.raises(ServiceError) as exists:
        export_eval_promotion("default", [feedback.feedback_id], cfg, output_path=str(output))
    assert exists.value.code == "INVALID_REQUEST"
