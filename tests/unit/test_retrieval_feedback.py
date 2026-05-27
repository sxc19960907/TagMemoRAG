from __future__ import annotations

import json

import pytest

from tagmemorag.config import Settings, StorageConfig
from tagmemorag.errors import ServiceError
from tagmemorag.eval.dataset import load_eval_suite
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
        "plan_id": "plan-1",
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
    assert reviewed.plan_id == "plan-1"
    assert list_feedback("default", cfg, status="new") == []
    triaged = list_feedback("default", cfg, status="triaged")[0]
    assert triaged.operator_note == "Good eval candidate."
    assert triaged.plan_id == "plan-1"


def test_review_overlay_can_add_expected_evidence_for_promotion(tmp_path):
    cfg = _settings(tmp_path)
    feedback = create_feedback(
        "default",
        _payload(feedback_id="fb-1", expected=[], selected_results=[], outcome="not_helpful"),
        cfg,
    )
    before = preview_eval_promotion("default", [feedback.feedback_id], cfg)
    assert before.cases == ()
    assert before.skipped[0]["reason"] == "no_usable_relevant_matcher"

    reviewed = review_feedback(
        "default",
        feedback.feedback_id,
        cfg,
        status="triaged",
        expected=[{"source_file": "coffee.md", "header": "服务模式", "text_contains": ["三秒"], "metadata": {"manual_id": "cm1"}}],
    )

    assert reviewed.expected[0].header == "服务模式"
    assert reviewed.status == "triaged"
    rows = list_feedback("default", cfg, status="triaged")
    assert rows[0].expected[0].text_contains == ("三秒",)
    after = preview_eval_promotion("default", [feedback.feedback_id], cfg)
    assert after.skipped == ()
    assert after.cases[0]["relevant"] == [
        {
            "source_file": "coffee.md",
            "header": "服务模式",
            "text_contains": ["三秒"],
            "metadata": {"manual_id": "cm1"},
        }
    ]


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
    assert preview.cases[0]["quality"] == {
        "level": "strong",
        "signals": ["text_contains"],
        "message": "Matcher has specific anchor or text evidence.",
    }
    assert preview.skipped == (
        {
            "feedback_id": "fb-bad",
            "reason": "no_usable_relevant_matcher",
            "outcome": "wrong_manual",
            "query": "E05 蒸汽异常怎么处理",
            "message": "No usable relevant matcher is available for this feedback.",
            "next_action": "Add expected evidence with source_file, header, anchor_key, text_contains, or metadata before promotion.",
        },
    )


def test_promotion_preview_marks_broad_matcher_as_weak(tmp_path):
    cfg = _settings(tmp_path)
    feedback = create_feedback(
        "default",
        _payload(feedback_id="fb-weak", expected=[{"source_file": "coffee.md", "header": "E05"}]),
        cfg,
    )

    preview = preview_eval_promotion("default", [feedback.feedback_id], cfg)

    assert preview.cases[0]["quality"]["level"] == "weak"
    assert preview.cases[0]["quality"]["signals"] == []
    assert "run browser eval" in preview.cases[0]["quality"]["message"]


def test_promotion_preview_explains_duplicate_case_skip(tmp_path):
    cfg = _settings(tmp_path)
    feedback = create_feedback("default", _payload(feedback_id="fb-1"), cfg)
    output = tmp_path / "eval_drafts" / "default" / "feedback.jsonl"
    output.parent.mkdir(parents=True)
    output.write_text('{"id": "feedback-fb-1", "query": "old"}\n', encoding="utf-8")

    preview = preview_eval_promotion("default", [feedback.feedback_id], cfg, output_path=str(output))

    assert preview.cases == ()
    assert preview.skipped == (
        {
            "feedback_id": "fb-1",
            "reason": "duplicate_case_id",
            "outcome": "missing_result",
            "query": "E05 蒸汽异常怎么处理",
            "message": "An eval case with this feedback id already exists at the output path.",
            "next_action": "Choose append/overwrite intentionally or keep the existing eval case.",
            "case_id": "feedback-fb-1",
        },
    )


def test_export_eval_promotion_requires_explicit_existing_file_mode_and_marks_promoted(tmp_path):
    cfg = _settings(tmp_path)
    feedback = create_feedback("default", _payload(feedback_id="fb-1"), cfg)
    output = tmp_path / "eval_drafts" / "default" / "feedback.jsonl"

    preview = export_eval_promotion("default", [feedback.feedback_id], cfg, output_path=str(output))
    assert preview.cases
    exported = preview.to_dict()
    assert exported["summary"]["ready_count"] == 1
    assert exported["summary"]["skipped_count"] == 0
    assert exported["summary"]["output_path"] == str(output)
    assert exported["summary"]["suite_path"] == str(output)
    assert exported["summary"]["report_path"] == str(output.with_name("feedback-report.json"))
    assert exported["summary"]["next_command"] == (
        f"tagmemorag eval run --suite {output} --reuse-built-kb --output {output.with_name('feedback-report.json')}"
    )
    assert "currently built KB" in exported["summary"]["command_note"]
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["id"] == "feedback-fb-1"
    cases = load_eval_suite(output)
    assert cases[0].id == "feedback-fb-1"
    assert cases[0].query == "E05 蒸汽异常怎么处理"
    assert cases[0].relevant[0].source_file == "coffee.md"
    assert list_feedback("default", cfg, status="promoted")[0].feedback_id == "fb-1"

    with pytest.raises(ServiceError) as exists:
        export_eval_promotion("default", [feedback.feedback_id], cfg, output_path=str(output))
    assert exists.value.code == "INVALID_REQUEST"


def test_promotion_summary_quotes_eval_command_paths(tmp_path):
    cfg = _settings(tmp_path)
    feedback = create_feedback("default", _payload(feedback_id="fb-1"), cfg)
    output = tmp_path / "eval_drafts" / "default dir" / "feedback file.jsonl"

    preview = preview_eval_promotion("default", [feedback.feedback_id], cfg, output_path=str(output)).to_dict()

    assert preview["summary"]["report_path"] == str(output.with_name("feedback file-report.json"))
    command = preview["summary"]["next_command"]
    assert "--reuse-built-kb" in command
    assert f"--suite '{output}'" in command
    assert f"--output '{output.with_name('feedback file-report.json')}'" in command
