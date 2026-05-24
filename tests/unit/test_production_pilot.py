from __future__ import annotations

import json

from tagmemorag.eval.dataset import EvalThresholds
from tagmemorag.production_pilot import (
    DEFAULT_ANSWER_QUALITY_SUITE,
    DEFAULT_PILOT_THRESHOLDS,
    PILOT_SCHEMA_VERSION,
    PilotStage,
    ProductionPilotReport,
    run_production_pilot,
    write_pilot_report,
)


def _local_config(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
model:
  provider: hashing
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
vector_store:
  provider: npz
manual_library:
  root_dir: {tmp_path / "manuals"}
  registry_backend: file
  blob_backend: local
  blob_root_dir: {tmp_path / "blobs"}
""",
        encoding="utf-8",
    )
    return config


def test_production_pilot_runs_local_profile_and_sanitizes_eval(tmp_path):
    report = run_production_pilot(
        config_path=_local_config(tmp_path),
        suite_path="tests/fixtures/eval/coffee.jsonl",
        docs_path="tests/fixtures",
        workdir=tmp_path / "pilot",
        thresholds=DEFAULT_PILOT_THRESHOLDS,
    )

    assert report.status == "passed"
    body = report.to_dict()
    assert body["schema_version"] == PILOT_SCHEMA_VERSION
    assert [stage["name"] for stage in body["stages"]] == [
        "config_validate",
        "provider_probe",
        "readiness_smoke",
        "answer_quality",
        "eval",
    ]
    answer_quality = next(stage for stage in body["stages"] if stage["name"] == "answer_quality")
    assert answer_quality["status"] == "passed"
    assert answer_quality["detail"]["suite"] == "basic.jsonl"
    assert answer_quality["detail"]["cases"] == 5
    assert answer_quality["detail"]["failed"] == 0
    eval_stage = next(stage for stage in body["stages"] if stage["name"] == "eval")
    assert eval_stage["detail"]["cases"] == 7
    assert eval_stage["detail"]["metrics"]["recall_at_k"] >= 0.75

    serialized = json.dumps(body, ensure_ascii=False)
    assert "蒸汽很小怎么办" not in serialized
    assert "喷嘴堵塞会造成蒸汽变小" not in serialized
    assert "pump must be replaced immediately" not in serialized
    assert "scale in the steam nozzle" not in serialized
    assert "actual_top_k" not in serialized
    assert "Authorization" not in serialized


def test_production_pilot_can_skip_answer_quality_stage(tmp_path):
    report = run_production_pilot(
        config_path=_local_config(tmp_path),
        suite_path="tests/fixtures/eval/coffee.jsonl",
        docs_path="tests/fixtures",
        workdir=tmp_path / "pilot",
        thresholds=DEFAULT_PILOT_THRESHOLDS,
        skip_answer_quality=True,
    )

    assert report.status == "passed"
    assert "answer_quality" not in [stage.name for stage in report.stages]


def test_production_pilot_answer_quality_suite_can_be_overridden(tmp_path):
    suite = tmp_path / "answer-quality.jsonl"
    suite.write_text(
        '{"id":"local-pass","question":"What color is the reset button?",'
        '"contexts":[{"citation_id":"cit_001","text":"The reset button is red."}],'
        '"answer":"The reset button is red [cit_001]. {{support:reset button is red}}",'
        '"expected":{"grounded":true,"relevant":true,"citation_supported":true}}'
        "\n",
        encoding="utf-8",
    )

    report = run_production_pilot(
        config_path=_local_config(tmp_path),
        suite_path="tests/fixtures/eval/coffee.jsonl",
        docs_path="tests/fixtures",
        workdir=tmp_path / "pilot",
        thresholds=DEFAULT_PILOT_THRESHOLDS,
        answer_quality_suite_path=suite,
    )

    stage = next(stage for stage in report.stages if stage.name == "answer_quality")
    assert stage.status == "passed"
    assert stage.detail["suite"] == "answer-quality.jsonl"
    assert stage.detail["cases"] == 1


def test_production_pilot_answer_quality_invalid_suite_fails(tmp_path):
    missing = tmp_path / "missing.jsonl"

    report = run_production_pilot(
        config_path=_local_config(tmp_path),
        suite_path="tests/fixtures/eval/coffee.jsonl",
        docs_path="tests/fixtures",
        workdir=tmp_path / "pilot",
        thresholds=DEFAULT_PILOT_THRESHOLDS,
        answer_quality_suite_path=missing,
    )

    assert report.status == "failed"
    stage = next(stage for stage in report.stages if stage.name == "answer_quality")
    assert stage.status == "failed"
    assert stage.error is not None
    assert stage.error["type"] == "EvalSuiteError"
    assert stage.detail["suite"] == "missing.jsonl"


def test_production_pilot_includes_eval_reauthoring_warning_stage(tmp_path):
    report = run_production_pilot(
        config_path=_local_config(tmp_path),
        suite_path="tests/fixtures/eval/coffee.jsonl",
        docs_path="tests/fixtures",
        workdir=tmp_path / "pilot",
        thresholds=DEFAULT_PILOT_THRESHOLDS,
        hashing_baseline_path="tests/fixtures/eval/baselines/hashing.json",
        production_baseline_path="tests/fixtures/eval/baselines/siliconflow.json",
    )

    assert report.status == "warning"
    stage = next(stage for stage in report.stages if stage.name == "eval_reauthoring_diagnosis")
    assert stage.status == "warning"
    assert stage.detail["schema_version"] == "eval_reauthoring_diagnosis.v1"
    assert stage.detail["highest_severity"] == 3
    assert stage.detail["highest_blocking_severity"] == 3
    assert stage.detail["status_counts"]["investigate"] >= 1
    assert len(stage.detail["top_suites"]) <= 5
    serialized = json.dumps(stage.to_dict(), ensure_ascii=False)
    assert "蒸汽很小怎么办" not in serialized
    assert "actual_top_k" not in serialized


def test_production_pilot_informational_diagnosis_can_pass_stage(tmp_path):
    informational_suites = [
        "cross_kb_negatives.jsonl",
        "fault_codes.jsonl",
        "model_numbers.jsonl",
        "tag_cooccurrence.jsonl",
    ]
    accepted_suites = [
        "coffee.jsonl",
        "mixed_language.jsonl",
        "product_manuals.jsonl",
        "tag_rerank_edge.jsonl",
    ]

    report = run_production_pilot(
        config_path=_local_config(tmp_path),
        suite_path="tests/fixtures/eval/coffee.jsonl",
        docs_path="tests/fixtures",
        workdir=tmp_path / "pilot",
        thresholds=DEFAULT_PILOT_THRESHOLDS,
        hashing_baseline_path="tests/fixtures/eval/baselines/hashing.json",
        production_baseline_path="tests/fixtures/eval/baselines/siliconflow.json",
        informational_suites=informational_suites,
        accepted_suites=accepted_suites,
    )

    assert report.status == "passed"
    stage = next(stage for stage in report.stages if stage.name == "eval_reauthoring_diagnosis")
    assert stage.status == "passed"
    assert stage.detail["highest_severity"] == 3
    assert stage.detail["highest_blocking_severity"] == 0
    assert stage.detail["informational_count"] == len(informational_suites)
    assert stage.detail["accepted_count"] == len(accepted_suites)
    assert all(suite["informational"] or suite["accepted"] for suite in stage.detail["top_suites"])


def test_production_pilot_requires_both_baselines_for_diagnosis(tmp_path):
    report = run_production_pilot(
        config_path=_local_config(tmp_path),
        suite_path="tests/fixtures/eval/coffee.jsonl",
        docs_path="tests/fixtures",
        workdir=tmp_path / "pilot",
        thresholds=DEFAULT_PILOT_THRESHOLDS,
        hashing_baseline_path="tests/fixtures/eval/baselines/hashing.json",
    )

    assert report.status == "failed"
    stage = next(stage for stage in report.stages if stage.name == "eval_reauthoring_diagnosis")
    assert stage.status == "failed"
    assert stage.error["reason"] == "both_hashing_and_production_baselines_required"


def test_production_pilot_failure_aggregates_eval_threshold(tmp_path):
    report = run_production_pilot(
        config_path=_local_config(tmp_path),
        suite_path="tests/fixtures/eval/coffee.jsonl",
        docs_path="tests/fixtures",
        workdir=tmp_path / "pilot",
        thresholds=EvalThresholds(min_recall_at_k=1.0, min_mrr=1.0, min_hit_at_k=1.0),
    )

    assert report.status == "failed"
    eval_stage = next(stage for stage in report.stages if stage.name == "eval")
    assert eval_stage.status == "failed"
    assert eval_stage.error is not None
    assert eval_stage.error["type"] == "EvalThreshold"


def test_production_pilot_markdown_and_writer(tmp_path):
    report = ProductionPilotReport(
        status="warning",
        config_path="config.yaml",
        suite_path="suite.jsonl",
        docs_path="docs",
        workdir=str(tmp_path),
        stages=[PilotStage("config_validate", "warning", {"checks": {"warning": 1}})],
        next_steps=["Review warning stages."],
    )

    markdown = report.to_markdown()
    assert "# TagMemoRAG Production Pilot Report" in markdown
    assert "| `config_validate` | `warning` |" in markdown

    output = tmp_path / "pilot.md"
    write_pilot_report(report, output, fmt="markdown")
    assert output.read_text(encoding="utf-8") == markdown


def test_default_answer_quality_suite_points_to_checked_in_fixture():
    assert DEFAULT_ANSWER_QUALITY_SUITE == "tests/fixtures/answer_quality/basic.jsonl"
