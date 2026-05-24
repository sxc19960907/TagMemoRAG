from __future__ import annotations

import json
from pathlib import Path
import sys

from tagmemorag.same_page_ordering_candidate import (
    SCHEMA_VERSION,
    run_same_page_ordering_candidate,
    write_candidate_ranking_pressure,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import diag_same_page_candidate as candidate_cli  # noqa: E402


def test_candidate_improves_same_page_matched_evidence(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            _case(
                "github-repo",
                results=[
                    _result(3.2, "github.md", "Hello", "Create a branch and click around.", []),
                    _result(2.8, "github.md", "Hello", "A repository is a folder that contains README files.", [0]),
                ],
            )
        ],
    )

    body = run_same_page_ordering_candidate(report_path).to_dict()

    assert body["schema_version"] == SCHEMA_VERSION
    assert body["status"] == "passed"
    assert body["candidate_summary"]["improved_cases"] == 1
    assert body["candidate_summary"]["regressed_cases"] == 0
    case = body["cases"][0]
    assert case["baseline_first_matched_rank"] == 2
    assert case["candidate_first_matched_rank"] == 1
    assert case["matched_rank_delta"] == 1
    assert case["candidate_metrics"]["mrr"] == 1.0


def test_candidate_leaves_cross_page_case_unchanged(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            _case(
                "cross-page",
                results=[
                    _result(3.2, "a.md", "A", "Create a branch.", []),
                    _result(2.8, "b.md", "B", "A repository is a folder.", [0]),
                ],
            )
        ],
    )

    case = run_same_page_ordering_candidate(report_path).to_dict()["cases"][0]

    assert case["same_page_dominant"] is False
    assert case["changed"] is False
    assert case["baseline_first_matched_rank"] == case["candidate_first_matched_rank"]


def test_candidate_leaves_rank_one_same_page_case_unchanged(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            _case(
                "rank-one",
                results=[
                    _result(3.2, "same.md", "Same", "README note.", [0]),
                    _result(2.8, "same.md", "Same", "A repository is a folder that contains README files.", []),
                ],
            )
        ],
    )

    case = run_same_page_ordering_candidate(report_path).to_dict()["cases"][0]

    assert case["same_page_dominant"] is True
    assert case["changed"] is False
    assert case["regressed"] is False
    assert case["candidate_first_matched_rank"] == 1


def test_candidate_detects_pressure_case_regression(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            _case(
                "regression",
                results=[
                    _result(3.2, "same.md", "Same", "A repository is a collection that includes branches.", []),
                    _result(2.9, "same.md", "Same", "README note.", [0]),
                    _result(2.8, "same.md", "Same", "A repository is a folder that contains README files.", []),
                ],
            )
        ],
    )

    body = run_same_page_ordering_candidate(report_path).to_dict()

    assert body["status"] == "failed"
    assert body["candidate_summary"]["regressed_cases"] == 1
    assert body["cases"][0]["baseline_first_matched_rank"] == 2
    assert body["cases"][0]["candidate_first_matched_rank"] == 3


def test_report_omits_query_raw_text_and_actual_top_k(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            _case(
                "private",
                query="sensitive query should not appear",
                results=[
                    _result(3.0, "same.md", "Same", "raw snippet should not leak", []),
                    _result(2.0, "same.md", "Same", "matched raw snippet should not leak", [0]),
                ],
            )
        ],
    )

    serialized = run_same_page_ordering_candidate(report_path).to_json()

    assert "sensitive query should not appear" not in serialized
    assert "raw snippet should not leak" not in serialized
    assert "matched raw snippet should not leak" not in serialized
    assert "actual_top_k" not in serialized


def test_markdown_rendering_contains_bounded_summary(tmp_path):
    report_path = _write_report(tmp_path, [_case("github-repo")])

    markdown = run_same_page_ordering_candidate(report_path).to_markdown()

    assert markdown.startswith("# Same-Page Ordering Candidate")
    assert "| `github-repo` |" in markdown
    assert "A repository is a folder" not in markdown


def test_candidate_pressure_output_is_bounded(tmp_path):
    report_path = _write_report(tmp_path, [_case("github-repo")])
    output = tmp_path / "candidate-pressure.json"
    report = run_same_page_ordering_candidate(report_path)

    write_candidate_ranking_pressure(report, output)
    body = json.loads(output.read_text(encoding="utf-8"))

    assert body["schema_version"] == "general_web_ranking_pressure.v1"
    assert body["summary"]["ranking_pressure_count"] == 0
    assert "actual_top_k" not in json.dumps(body, ensure_ascii=False)


def test_cli_writes_json_and_candidate_pressure(tmp_path, capsys):
    report_path = _write_report(tmp_path, [_case("github-repo")])
    output = tmp_path / "candidate.json"
    pressure = tmp_path / "candidate-pressure.json"

    exit_code = candidate_cli.main(
        [
            "--report",
            str(report_path),
            "--output",
            str(output),
            "--candidate-ranking-pressure-output",
            str(pressure),
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == SCHEMA_VERSION
    assert pressure.exists()


def test_cli_invalid_report_returns_two(tmp_path, capsys):
    exit_code = candidate_cli.main(["--report", str(tmp_path / "missing.json")])

    assert exit_code == 2
    assert "eval report not found" in capsys.readouterr().err


def _write_report(tmp_path: Path, cases: list[dict]) -> Path:
    report_path = tmp_path / "general-web.json"
    report_path.write_text(
        json.dumps(
            {
                "suite": "tests/fixtures/eval/general_web.jsonl",
                "summary": {"cases": len(cases), "passed": True, "recall_at_k": 1.0, "mrr": 0.5, "hit_at_k": 1.0},
                "cases": cases,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return report_path


def _case(
    case_id: str,
    *,
    query: str = "what is a github repository README",
    results: list[dict] | None = None,
) -> dict:
    return {
        "id": case_id,
        "query": query,
        "kb_name": "general_web",
        "metrics": {"precision_at_k": 0.25, "recall_at_k": 1.0, "mrr": 0.5, "hit_at_k": 1.0},
        "expected": [{"source_file": "github.md"}],
        "actual_top_k": results
        or [
            _result(3.2, "github.md", "Hello", "Create and review changes.", []),
            _result(2.8, "github.md", "Hello", "A repository is a folder that contains a README.", [0]),
        ],
    }


def _result(score: float, source_file: str, header: str, text: str, matched: list[int]) -> dict:
    return {
        "score": score,
        "source_file": source_file,
        "header": header,
        "text": text,
        "matched_expected_indexes": matched,
    }
