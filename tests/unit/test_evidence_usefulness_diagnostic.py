from __future__ import annotations

import json
from pathlib import Path
import sys

from tagmemorag.evidence_usefulness_diagnostic import SCHEMA_VERSION, summarize_evidence_usefulness

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import diag_evidence_usefulness as diag_cli  # noqa: E402


def test_usefulness_detects_matched_evidence_beating_prior_noise(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            _case(
                "repo",
                results=[
                    _result("overview.md", "Navigation", "Source: https://example.test Navigation table of contents", []),
                    _result(
                        "body.md",
                        "Repository",
                        "A repository is a folder that contains files, README content, and project history.",
                        [0],
                    ),
                ],
            )
        ],
    )

    body = summarize_evidence_usefulness(report_path).to_dict()

    assert body["schema_version"] == SCHEMA_VERSION
    assert body["summary"]["cases"] == 1
    assert body["summary"]["matched_cases"] == 1
    assert body["summary"]["matched_beats_pre_match_count"] == 1
    assert body["summary"]["useful_evidence_under_ranked_count"] == 0
    case = body["cases"][0]
    assert case["case_id"] == "repo"
    assert case["first_matched_rank"] == 2
    assert case["results"][1]["matched"] is True
    assert case["results"][1]["definition_cues"] >= 1
    assert case["results"][1]["query_term_coverage"] > 0.0


def test_usefulness_marks_useful_evidence_under_ranked_when_prior_scores_higher(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            _case(
                "pull-request",
                results=[
                    _result(
                        "noise.md",
                        "Pull request overview",
                        "A pull request is a request to merge changes and can be reviewed by collaborators.",
                        [],
                    ),
                    _result("matched.md", "Pull requests", "Pull requests let you tell others about changes.", [0]),
                ],
            )
        ],
    )

    case = summarize_evidence_usefulness(report_path).to_dict()["cases"][0]

    assert case["first_matched_rank"] == 2
    assert case["useful_evidence_under_ranked"] is True
    assert case["matched_beats_pre_match"] is False


def test_report_omits_query_raw_text_and_actual_top_k(tmp_path):
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

    serialized = summarize_evidence_usefulness(report_path).to_json()

    assert "sensitive query should not appear" not in serialized
    assert "raw snippet should not leak" not in serialized
    assert "matched raw snippet should not leak" not in serialized
    assert "actual_top_k" not in serialized


def test_markdown_rendering_contains_only_bounded_fields(tmp_path):
    report_path = _write_report(tmp_path, [_case("repo")])

    markdown = summarize_evidence_usefulness(report_path).to_markdown()

    assert markdown.startswith("# Evidence Usefulness Diagnostic")
    assert "| `repo` | 2 |" in markdown
    assert "score=" in markdown
    assert "A repository is a folder" not in markdown


def test_cli_writes_json_file(tmp_path, capsys):
    report_path = _write_report(tmp_path, [_case("repo")])
    output = tmp_path / "usefulness.json"

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
            _result("body.md", "Body", "A repository is a folder that contains a README.", [0]),
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
