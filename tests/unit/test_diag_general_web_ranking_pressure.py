from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import diag_general_web_ranking_pressure as diag  # noqa: E402


def test_ranking_pressure_detects_under_ranked_relevant_evidence(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            _case(
                "repo",
                metrics={"precision_at_k": 0.25, "recall_at_k": 1.0, "mrr": 0.5, "hit_at_k": 1.0},
                results=[
                    _result("overview.md", "Hello", "This tutorial teaches GitHub essentials. Click create and review.", []),
                    _result("body.md", "Hello", "A repository is a folder that contains related items.", [0]),
                ],
            )
        ],
    )

    report = diag.summarize_ranking_pressure(report_path)
    body = report.to_dict()

    assert body["schema_version"] == "general_web_ranking_pressure.v1"
    assert body["summary"]["ranking_pressure_count"] == 1
    item = body["items"][0]
    assert item["case_id"] == "repo"
    assert item["first_matched_rank"] == 2
    assert item["pressure_rank_count"] == 1
    assert item["matched_expected_indexes"] == [0]
    assert item["top_results"][0]["action_cues"] >= 2
    assert item["top_results"][1]["definition_cues"] >= 1


def test_report_omits_query_and_raw_text(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            _case(
                "private-query",
                query="sensitive query should not appear",
                results=[
                    _result("a.md", "A", "raw snippet should not leak", []),
                    _result("b.md", "B", "matched raw snippet should not leak", [0]),
                ],
            )
        ],
    )

    serialized = diag.summarize_ranking_pressure(report_path).to_json()

    assert "sensitive query should not appear" not in serialized
    assert "raw snippet should not leak" not in serialized
    assert "matched raw snippet should not leak" not in serialized


def test_top_k_miss_is_not_ranking_pressure(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            _case(
                "miss",
                metrics={"precision_at_k": 0.0, "recall_at_k": 0.0, "mrr": 0.0, "hit_at_k": 0.0},
                results=[_result("x.md", "X", "unmatched", [])],
            )
        ],
    )

    report = diag.summarize_ranking_pressure(report_path)

    assert report.items == []


def test_markdown_rendering_contains_bounded_cue_summary(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            _case(
                "pull-request",
                results=[
                    _result("overview.md", "Hello", "This tutorial is a quickstart overview.", []),
                    _result("pr.md", "Hello", "Pull requests are the heart of collaboration.", [0]),
                ],
            )
        ],
    )

    markdown = diag.summarize_ranking_pressure(report_path).to_markdown()

    assert markdown.startswith("# General-Web Ranking Pressure")
    assert "| `pull-request` | 2 |" in markdown
    assert "overview=" in markdown
    assert "Pull requests are the heart" not in markdown


def test_cli_writes_json_file(tmp_path, capsys):
    report_path = _write_report(tmp_path, [_case("repo")])
    output = tmp_path / "pressure.json"

    exit_code = diag.main(["--report", str(report_path), "--output", str(output)])

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == "general_web_ranking_pressure.v1"


def test_cli_invalid_report_returns_two(tmp_path, capsys):
    exit_code = diag.main(["--report", str(tmp_path / "missing.json")])

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
    query: str = "query text",
    metrics: dict | None = None,
    results: list[dict] | None = None,
) -> dict:
    return {
        "id": case_id,
        "query": query,
        "kb_name": "general_web",
        "metrics": metrics or {"precision_at_k": 0.25, "recall_at_k": 1.0, "mrr": 0.5, "hit_at_k": 1.0},
        "expected": [{"source_file": "body.md"}],
        "actual_top_k": results
        or [
            _result("overview.md", "Overview", "This tutorial teaches broad concepts.", []),
            _result("body.md", "Body", "A repository is a folder.", [0]),
        ],
    }


def _result(source_file: str, header: str, text: str, matched: list[int]) -> dict:
    return {
        "source_file": source_file,
        "header": header,
        "text": text,
        "matched_expected_indexes": matched,
        "score": 1.0,
    }
