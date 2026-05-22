from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tagmemorag.eval.answer_quality import (
    ANSWER_QUALITY_SCHEMA_VERSION,
    evaluate_answer_quality_case,
    load_answer_quality_suite,
    run_answer_quality_diagnostics,
)
from tagmemorag.eval.dataset import EvalSuiteError


FIXTURE = Path("tests/fixtures/answer_quality/basic.jsonl")


def test_load_answer_quality_suite_valid():
    cases = load_answer_quality_suite(FIXTURE)

    assert [case.id for case in cases] == [
        "grounded-steam-cleaning",
        "ungrounded-filter-claim",
        "insufficient-evidence-refusal",
        "citation-miss-steam-cleaning",
        "conflicting-evidence-unsupported-choice",
    ]
    assert cases[0].contexts[0].citation_id == "cit_001"
    assert cases[0].expected.grounded is True


def test_load_answer_quality_suite_rejects_duplicate_id(tmp_path):
    suite = tmp_path / "suite.jsonl"
    suite.write_text(
        "\n".join(
            [
                '{"id":"dup","question":"q","answer":"a [cit_1]","contexts":[{"citation_id":"cit_1"}],"expected":{"grounded":true}}',
                '{"id":"dup","question":"q","answer":"a [cit_1]","contexts":[{"citation_id":"cit_1"}],"expected":{"grounded":true}}',
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(EvalSuiteError, match="duplicate case id: dup"):
        load_answer_quality_suite(suite)


def test_evaluate_answer_quality_case_detects_ungrounded_fixture():
    case = [item for item in load_answer_quality_suite(FIXTURE) if item.id == "ungrounded-filter-claim"][0]

    result = evaluate_answer_quality_case(case)

    assert result.passed
    assert result.observed["grounded"] is False
    assert result.scores["grounded"] == 0.0


def test_evaluate_answer_quality_case_flags_unknown_citation(tmp_path):
    suite = tmp_path / "suite.jsonl"
    suite.write_text(
        '{"id":"unknown-citation","question":"steam","answer":"Clean the nozzle [cit_fake].",'
        '"contexts":[{"citation_id":"cit_1","text":"Clean the nozzle."}],'
        '"expected":{"grounded":true,"citation_supported":true}}\n',
        encoding="utf-8",
    )
    case = load_answer_quality_suite(suite)[0]

    result = evaluate_answer_quality_case(case)

    assert not result.passed
    assert "citation_supported expected True observed False" in result.failures
    assert result.warnings == ["unknown citations: cit_fake"]


def test_run_answer_quality_diagnostics_report_is_bounded():
    report = run_answer_quality_diagnostics(FIXTURE)
    body = report.to_dict()
    serialized = report.to_json()

    assert body["schema_version"] == ANSWER_QUALITY_SCHEMA_VERSION
    assert body["summary"]["passed"] is True
    assert body["summary"]["cases"] == 5
    assert "scale in the steam nozzle" not in serialized
    assert "water filter is expired" not in serialized
    assert "pump must be replaced immediately" not in serialized


def test_answer_quality_cli_writes_report(tmp_path):
    report_path = tmp_path / "answer-quality.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tagmemorag",
            "eval",
            "answer-quality",
            "--suite",
            str(FIXTURE),
            "--output",
            str(report_path),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "answer-quality eval passed: cases=5" in result.stdout
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"]["passed"] is True
    assert report["summary"]["cases"] == 5
    assert report["cases"][0]["id"] == "grounded-steam-cleaning"
