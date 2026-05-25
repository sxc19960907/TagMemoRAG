from __future__ import annotations

import json

from tagmemorag.release_readiness import (
    RELEASE_READINESS_SCHEMA_VERSION,
    DEFAULT_REPORT_PATHS,
    run_release_readiness,
    write_release_readiness_report,
)


def _write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _reports(tmp_path):
    paths = {}
    for name in DEFAULT_REPORT_PATHS:
        path = tmp_path / f"{name}.json"
        paths[name] = str(path)
    for name in ("general_web_retrieval", "multiformat_retrieval", "mixed_domain_retrieval", "realmanuals_retrieval"):
        _write(
            tmp_path / f"{name}.json",
            {"summary": {"cases": 3, "hit_at_k": 1.0, "recall_at_k": 1.0, "mrr": 1.0, "passed": True}},
        )
    for name in ("general_web_context", "general_web_context_tight", "multiformat_context", "multiformat_context_tight"):
        _write(
            tmp_path / f"{name}.json",
            {
                "schema_version": "context_quality_eval.v1",
                "summary": {
                    "cases": 3,
                    "cases_with_expected_retrieved": 3,
                    "cases_with_expected_selected": 3,
                    "selected_expected_rate": 1.0,
                },
            },
        )
    for name in ("general_web_answer", "multiformat_answer"):
        _write(tmp_path / f"{name}.json", {"summary": {"cases": 3, "failed": 0, "passed": True}})
    _write(
        tmp_path / "product_qa_answer_quality.json",
        {
            "schema_version": "answer_quality.v1",
            "summary": {
                "cases": 2,
                "passed": True,
                "dimensions": {
                    "grounded": {"passed": 2, "failed": 0},
                    "relevant": {"passed": 2, "failed": 0},
                },
            },
        },
    )
    return paths


def test_release_readiness_passes_clean_report_set(tmp_path):
    report = run_release_readiness(report_paths=_reports(tmp_path))

    body = report.to_dict()

    assert body["schema_version"] == RELEASE_READINESS_SCHEMA_VERSION
    assert body["status"] == "passed"
    assert all(stage["status"] == "passed" for stage in body["stages"])
    assert "actual_top_k" not in json.dumps(body, ensure_ascii=False)


def test_release_readiness_surfaces_optional_ranking_pressure_without_warning(tmp_path):
    paths = _reports(tmp_path)
    _write(
        tmp_path / "general_web_ranking_pressure.json",
        {
            "schema_version": "general_web_ranking_pressure.v1",
            "summary": {
                "ranking_pressure_count": 2,
                "highest_pressure_rank_count": 5,
            },
            "items": [
                {
                    "case_id": "github-hello-world-repository",
                    "top_results": [{"rank": 1, "action_cues": 6}],
                }
            ],
        },
    )

    report = run_release_readiness(report_paths=paths)
    body = report.to_dict()
    general_web = next(stage for stage in body["stages"] if stage["name"] == "general_web_retrieval")
    serialized = json.dumps(body, ensure_ascii=False)

    assert body["status"] == "passed"
    assert general_web["status"] == "passed"
    assert general_web["detail"]["ranking_pressure_count"] == 2
    assert general_web["detail"]["highest_pressure_rank_count"] == 5
    assert any("non-blocking general-web ranking pressure" in step for step in body["next_steps"])
    assert "github-hello-world-repository" not in serialized
    assert "top_results" not in serialized


def test_release_readiness_ignores_missing_optional_ranking_pressure_report(tmp_path):
    paths = _reports(tmp_path)
    paths["general_web_ranking_pressure"] = str(tmp_path / "missing-ranking-pressure.json")

    report = run_release_readiness(report_paths=paths)
    body = report.to_dict()
    general_web = next(stage for stage in body["stages"] if stage["name"] == "general_web_retrieval")

    assert body["status"] == "passed"
    assert "ranking_pressure_count" not in general_web["detail"]
    assert not any("ranking pressure" in step for step in body["next_steps"])


def test_release_readiness_ignores_malformed_optional_ranking_pressure_report(tmp_path):
    paths = _reports(tmp_path)
    _write(tmp_path / "general_web_ranking_pressure.json", ["not", "an", "object"])

    report = run_release_readiness(report_paths=paths)
    body = report.to_dict()
    general_web = next(stage for stage in body["stages"] if stage["name"] == "general_web_retrieval")

    assert body["status"] == "passed"
    assert "ranking_pressure_count" not in general_web["detail"]


def test_release_readiness_warns_for_known_current_quality_gaps(tmp_path):
    paths = _reports(tmp_path)
    _write(
        tmp_path / "general_web_retrieval.json",
        {"summary": {"cases": 7, "hit_at_k": 1.0, "recall_at_k": 0.928571, "mrr": 0.579932, "passed": False}},
    )
    _write(
        tmp_path / "multiformat_context_tight.json",
        {
            "summary": {
                "cases": 3,
                "cases_with_expected_retrieved": 3,
                "cases_with_expected_selected": 2,
                "selected_expected_rate": 0.666667,
            }
        },
    )

    report = run_release_readiness(report_paths=paths)
    stages = {stage.name: stage for stage in report.stages}

    assert report.status == "warning"
    assert stages["general_web_retrieval"].status == "warning"
    assert stages["multiformat_context_tight"].status == "warning"
    assert "MRR below release target" in stages["general_web_retrieval"].risks[0]
    assert "tight-budget context" in stages["multiformat_context_tight"].risks[0]


def test_release_readiness_fails_missing_required_report(tmp_path):
    paths = _reports(tmp_path)
    paths["general_web_answer"] = str(tmp_path / "missing.json")

    report = run_release_readiness(report_paths=paths)
    stage = next(stage for stage in report.stages if stage.name == "general_web_answer")

    assert report.status == "failed"
    assert stage.status == "failed"
    assert stage.error is not None
    assert stage.error["type"] == "ReportReadError"


def test_release_readiness_writes_markdown(tmp_path):
    report = run_release_readiness(report_paths=_reports(tmp_path))
    output = tmp_path / "readiness.md"

    write_release_readiness_report(report, output, fmt="markdown")

    text = output.read_text(encoding="utf-8")
    assert text.startswith("# TagMemoRAG Release Readiness Report")
    assert "| `general_web_retrieval` | `passed` |" in text
