from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import diagnose_eval_reauthoring as der  # noqa: E402


def test_classify_suite_ok_when_metrics_are_close():
    row = der.classify_suite(
        "tag_rerank_edge.jsonl",
        {"precision_at_k": 0.8, "recall_at_k": 1.0, "mrr": 0.9, "hit_at_k": 1.0},
        {"precision_at_k": 0.7, "recall_at_k": 0.95, "mrr": 0.85, "hit_at_k": 1.0},
    )

    assert row.status == "ok"
    assert row.severity == 0
    assert row.delta["recall_at_k"] == -0.05


def test_classify_suite_monitor_and_reauthor_thresholds():
    monitor = der.classify_suite(
        "coffee.jsonl",
        {"precision_at_k": 0.3, "recall_at_k": 0.8, "mrr": 0.8, "hit_at_k": 1.0},
        {"precision_at_k": 0.2, "recall_at_k": 0.69, "mrr": 0.79, "hit_at_k": 1.0},
    )
    reauthor = der.classify_suite(
        "product_manuals.jsonl",
        {"precision_at_k": 0.2, "recall_at_k": 1.0, "mrr": 1.0, "hit_at_k": 1.0},
        {"precision_at_k": 0.1, "recall_at_k": 0.72, "mrr": 0.74, "hit_at_k": 0.9},
    )

    assert monitor.status == "monitor"
    assert monitor.severity == 1
    assert "recall_delta_lte_-0.10" in monitor.reasons
    assert reauthor.status == "reauthor"
    assert reauthor.severity == 2
    assert {"recall_delta_lte_-0.25", "mrr_delta_lte_-0.25"} <= set(reauthor.reasons)


def test_classify_suite_investigate_for_low_production_or_missing_suite():
    low = der.classify_suite(
        "fault_codes.jsonl",
        {"precision_at_k": 0.6, "recall_at_k": 1.0, "mrr": 0.9, "hit_at_k": 1.0},
        {"precision_at_k": 0.2, "recall_at_k": 0.4, "mrr": 0.4, "hit_at_k": 0.4},
    )
    missing = der.classify_suite("new_suite.jsonl", None, {"recall_at_k": 1.0})

    assert low.status == "investigate"
    assert low.severity == 3
    assert "production_hit_at_k_below_0.5" in low.reasons
    assert "production_recall_at_k_below_0.5" in low.reasons
    assert missing.status == "investigate"
    assert missing.reasons == ["suite_missing_from_hashing_baseline"]


def test_diagnose_reauthoring_outputs_sorted_json_and_markdown(tmp_path):
    hashing = tmp_path / "hashing.json"
    production = tmp_path / "siliconflow.json"
    _write_baseline(
        hashing,
        "hashing",
        {
            "ok.jsonl": {"precision_at_k": 0.5, "recall_at_k": 0.9, "mrr": 0.9, "hit_at_k": 1.0},
            "bad.jsonl": {"precision_at_k": 0.5, "recall_at_k": 1.0, "mrr": 1.0, "hit_at_k": 1.0},
        },
    )
    _write_baseline(
        production,
        "siliconflow",
        {
            "ok.jsonl": {"precision_at_k": 0.5, "recall_at_k": 0.88, "mrr": 0.88, "hit_at_k": 1.0},
            "bad.jsonl": {"precision_at_k": 0.1, "recall_at_k": 0.3, "mrr": 0.2, "hit_at_k": 0.3},
        },
    )

    report = der.diagnose_reauthoring(hashing, production)
    body = report.to_dict()

    assert body["schema_version"] == "eval_reauthoring_diagnosis.v1"
    assert body["summary"]["status_counts"] == {"investigate": 1, "ok": 1}
    assert [suite["suite"] for suite in body["suites"]] == ["bad.jsonl", "ok.jsonl"]
    markdown = report.to_markdown()
    assert "| `bad.jsonl` | `investigate` | 3 |" in markdown


def test_cli_writes_markdown_file(tmp_path, capsys):
    hashing = tmp_path / "hashing.json"
    production = tmp_path / "siliconflow.json"
    output = tmp_path / "report.md"
    metrics = {"precision_at_k": 0.5, "recall_at_k": 1.0, "mrr": 1.0, "hit_at_k": 1.0}
    _write_baseline(hashing, "hashing", {"suite.jsonl": metrics})
    _write_baseline(production, "siliconflow", {"suite.jsonl": metrics})

    exit_code = der.main([
        "--hashing-baseline",
        str(hashing),
        "--production-baseline",
        str(production),
        "--format",
        "markdown",
        "--output",
        str(output),
    ])

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    assert output.read_text(encoding="utf-8").startswith("# Eval Reauthoring Diagnosis")


def test_cli_returns_two_for_invalid_input(tmp_path, capsys):
    exit_code = der.main([
        "--hashing-baseline",
        str(tmp_path / "missing.json"),
        "--production-baseline",
        str(tmp_path / "also-missing.json"),
    ])

    assert exit_code == 2
    assert "baseline file not found" in capsys.readouterr().err


def test_committed_baselines_diagnose_without_network():
    report = der.diagnose_reauthoring()
    body = report.to_dict()

    assert body["summary"]["suite_count"] >= 8
    assert body["summary"]["highest_severity"] == 3
    statuses = {suite["suite"]: suite["status"] for suite in body["suites"]}
    assert statuses["fault_codes.jsonl"] == "investigate"
    assert statuses["tag_rerank_edge.jsonl"] == "monitor"


def _write_baseline(path: Path, embedder: str, suites: dict[str, dict[str, float]]) -> None:
    path.write_text(
        json.dumps({"embedder": embedder, "suites": suites}, ensure_ascii=False),
        encoding="utf-8",
    )
