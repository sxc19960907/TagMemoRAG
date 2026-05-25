from __future__ import annotations

import json
from pathlib import Path
import sys

from tagmemorag.same_page_ordering_diagnostic import SCHEMA_VERSION, summarize_same_page_ordering

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import diag_same_page_ordering as diag_cli  # noqa: E402


def test_same_page_diagnostic_detects_repeated_source_pressure(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            _case(
                "github-repo",
                results=[
                    _result(3.2, "github.md", "Hello World", "Create a branch and open the repository page.", []),
                    _result(3.1, "github.md", "Hello World", "Click README and review changes.", []),
                    _result(
                        2.8,
                        "github.md",
                        "Hello World",
                        "A repository is a folder that contains files, README content, and history.",
                        [0],
                    ),
                ],
            )
        ],
    )

    body = summarize_same_page_ordering(report_path).to_dict()

    assert body["schema_version"] == SCHEMA_VERSION
    assert body["summary"]["same_page_pressure_count"] == 1
    assert body["summary"]["same_page_not_usefulness_count"] == 1
    case = body["cases"][0]
    assert case["case_id"] == "github-repo"
    assert case["first_matched_rank"] == 3
    assert case["pressure_rank_count"] == 2
    assert case["repeated_source_file_count"] == 3
    assert case["top_to_first_match_score_gap"] == 0.4
    assert case["matched_beats_pre_match"] is True
    assert case["diagnosis"] == "same_page_ordering_not_usefulness"


def test_near_tie_count_tracks_scores_close_to_first_match(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            _case(
                "near-tie",
                results=[
                    _result(2.5, "same.md", "Same", "A pull request is a request to merge changes.", []),
                    _result(2.47, "same.md", "Same", "Pull requests let you tell others about changes.", [0]),
                ],
            )
        ],
    )

    case = summarize_same_page_ordering(report_path, near_tie_score_delta=0.05).to_dict()["cases"][0]

    assert case["near_tie_before_match_count"] == 1
    assert case["top_to_first_match_score_gap"] == 0.03


def test_non_pressure_or_cross_page_cases_are_omitted(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            _case("rank-one", results=[_result(3.0, "a.md", "A", "A repository is a folder.", [0])]),
            _case(
                "cross-page",
                results=[
                    _result(3.0, "a.md", "A", "A repository page.", []),
                    _result(2.0, "b.md", "B", "A repository is a folder.", [0]),
                ],
            ),
        ],
    )

    report = summarize_same_page_ordering(report_path)

    assert report.cases == []


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

    serialized = summarize_same_page_ordering(report_path).to_json()

    assert "sensitive query should not appear" not in serialized
    assert "raw snippet should not leak" not in serialized
    assert "matched raw snippet should not leak" not in serialized
    assert "actual_top_k" not in serialized


def test_markdown_rendering_contains_bounded_case_summary(tmp_path):
    report_path = _write_report(tmp_path, [_case("github-repo")])

    markdown = summarize_same_page_ordering(report_path).to_markdown()

    assert markdown.startswith("# Same-Page Ordering Diagnostic")
    assert "| `github-repo` |" in markdown
    assert "A repository is a folder" not in markdown


def test_cli_writes_json_file(tmp_path, capsys):
    report_path = _write_report(tmp_path, [_case("github-repo")])
    output = tmp_path / "same-page.json"

    exit_code = diag_cli.main(["--report", str(report_path), "--output", str(output)])

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == SCHEMA_VERSION


def test_cli_invalid_report_returns_two(tmp_path, capsys):
    exit_code = diag_cli.main(["--report", str(tmp_path / "missing.json")])

    assert exit_code == 2
    assert "eval report not found" in capsys.readouterr().err


def _write_report(tmp_path: Path, cases: list[dict]) -> Path:
    report_path = tmp_path / "general-web.json"
    report_path.write_text(
        json.dumps(
            {
                "suite": "tests/fixtures/eval/general_web.jsonl",
                "summary": {"cases": len(cases), "passed": True, "recall_at_k": 0.9, "mrr": 0.8, "hit_at_k": 1.0},
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
            _result(3.2, "github.md", "Hello World", "Create and review changes.", []),
            _result(2.8, "github.md", "Hello World", "A repository is a folder that contains a README.", [0]),
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
