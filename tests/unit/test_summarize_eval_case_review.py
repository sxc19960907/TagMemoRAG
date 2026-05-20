from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import summarize_eval_case_review as scr  # noqa: E402


def test_summarize_redacts_query_and_raw_result_text_by_default(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            {
                "id": "steam",
                "query": "蒸汽很小怎么办",
                "kb_name": "default",
                "metrics": {"precision_at_k": 0.2, "recall_at_k": 0.5, "mrr": 0.5, "hit_at_k": 1.0},
                "expected": [{"source_file": "coffee.md", "header": "蒸汽"}],
                "actual_top_k": [
                    {
                        "source_file": "coffee.md",
                        "header": "蒸汽",
                        "score": 0.9,
                        "matched_expected_indexes": [0],
                        "text": "raw snippet should not leak",
                        "metadata": {"secretish": "nope"},
                    }
                ],
                "failures": [],
            }
        ],
    )

    report = scr.summarize_eval_report(report_path)
    body = report.to_dict()
    serialized = json.dumps(body, ensure_ascii=False)

    assert body["schema_version"] == "eval_case_review.v1"
    assert body["items"][0]["case_id"] == "steam"
    assert body["items"][0]["status"] == "review"
    assert "query" not in body["items"][0]
    assert "蒸汽很小怎么办" not in serialized
    assert "raw snippet should not leak" not in serialized
    assert "secretish" not in serialized


def test_include_query_is_explicit(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            {
                "id": "steam",
                "query": "蒸汽很小怎么办",
                "metrics": {"recall_at_k": 0.0, "mrr": 0.0, "hit_at_k": 0.0},
            }
        ],
    )

    report = scr.summarize_eval_report(report_path, include_query=True)

    assert report.items[0].query == "蒸汽很小怎么办"


def test_negative_hits_and_failures_are_urgent(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            {
                "id": "negative-case",
                "metrics": {"recall_at_k": 1.0, "mrr": 1.0, "hit_at_k": 1.0},
                "expected": [{"source_file": "a.md"}],
                "actual_top_k": [{"source_file": "a.md", "header": "A", "matched_expected_indexes": [0]}],
                "negative_hits": [{"rank": 1, "negative_index": 0, "source_file": "b.md"}],
                "failures": ["negative #0 matched at rank 1 (b.md)"],
            }
        ],
    )

    report = scr.summarize_eval_report(report_path)
    item = report.items[0]

    assert item.status == "urgent"
    assert item.severity == 3
    assert {"has_failures", "has_negative_hits"} <= set(item.reasons)
    assert item.negative_hits == [{"rank": 1, "negative_index": 0, "source_file": "b.md"}]


def test_include_ok_controls_clean_cases(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            {
                "id": "ok-case",
                "metrics": {"recall_at_k": 1.0, "mrr": 1.0, "hit_at_k": 1.0},
                "expected": [{"source_file": "a.md"}],
                "actual_top_k": [{"source_file": "a.md", "header": "A", "matched_expected_indexes": [0]}],
            }
        ],
    )

    hidden = scr.summarize_eval_report(report_path)
    included = scr.summarize_eval_report(report_path, include_ok=True)

    assert hidden.items == []
    assert included.items[0].status == "ok"
    assert included.items[0].severity == 0


def test_markdown_sorts_by_severity_and_limits_top_results(tmp_path):
    report_path = _write_report(
        tmp_path,
        [
            {
                "id": "mild",
                "metrics": {"recall_at_k": 0.9, "mrr": 0.9, "hit_at_k": 1.0},
                "expected": [{"source_file": "a.md"}, {"source_file": "b.md"}],
                "actual_top_k": [{"source_file": "a.md", "header": "A", "matched_expected_indexes": [0]}],
            },
            {
                "id": "urgent",
                "metrics": {"recall_at_k": 0.0, "mrr": 0.0, "hit_at_k": 0.0},
                "expected": [{"source_file": "c.md"}],
                "actual_top_k": [{"source_file": "x.md", "header": "X", "matched_expected_indexes": []}],
            },
        ],
    )

    report = scr.summarize_eval_report(report_path, max_results=1)
    markdown = report.to_markdown()

    assert [item.case_id for item in report.items] == ["urgent", "mild"]
    assert "| `urgent` | `urgent` | 3 |" in markdown
    assert "1:x.md#X" in markdown


def test_cli_writes_json_file(tmp_path, capsys):
    report_path = _write_report(
        tmp_path,
        [{"id": "case", "metrics": {"recall_at_k": 0.0, "mrr": 0.0, "hit_at_k": 0.0}}],
    )
    output = tmp_path / "review.json"

    exit_code = scr.main(["--report", str(report_path), "--output", str(output)])

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == "eval_case_review.v1"


def test_cli_invalid_report_returns_two(tmp_path, capsys):
    exit_code = scr.main(["--report", str(tmp_path / "missing.json")])

    assert exit_code == 2
    assert "eval report not found" in capsys.readouterr().err


def _write_report(tmp_path: Path, cases: list[dict]) -> Path:
    report = tmp_path / "eval-report.json"
    report.write_text(
        json.dumps(
            {
                "suite": "suite.jsonl",
                "summary": {"cases": len(cases), "passed": False, "recall_at_k": 0.5, "mrr": 0.5, "hit_at_k": 1.0},
                "cases": cases,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return report
