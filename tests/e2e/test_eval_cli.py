from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_eval_cli_passes_coffee_fixture(tmp_path):
    config = _write_hashing_config(tmp_path)
    report_path = tmp_path / "report.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tagmemorag",
            "eval",
            "run",
            "--suite",
            str(Path("tests/fixtures/eval/coffee.jsonl")),
            "--docs",
            str(Path("tests/fixtures")),
            "--config",
            str(config),
            "--output",
            str(report_path),
            "--eval-data-dir",
            str(tmp_path / "eval-data"),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"]["passed"] is True
    assert report["summary"]["cases"] == 7
    assert report["cases"][0]["actual_top_k"]


def test_eval_cli_passes_product_manual_fixture(tmp_path):
    config = _write_hashing_config(tmp_path)
    report_path = tmp_path / "product-report.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tagmemorag",
            "eval",
            "run",
            "--suite",
            str(Path("tests/fixtures/eval/product_manuals.jsonl")),
            "--docs",
            str(Path("tests/fixtures/product_manuals")),
            "--config",
            str(config),
            "--output",
            str(report_path),
            "--eval-data-dir",
            str(tmp_path / "eval-product-data"),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"]["passed"] is True
    assert report["summary"]["cases"] == 14
    assert report["cases"][0]["search_strategy"] == "exact_local"
    assert report["cases"][0]["expected"][0]["metadata"]["manual_id"] == "fridge-nrk6192"


def test_eval_cli_fails_threshold(tmp_path):
    config = _write_hashing_config(tmp_path)
    report_path = tmp_path / "report.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tagmemorag",
            "eval",
            "run",
            "--suite",
            str(Path("tests/fixtures/eval/coffee.jsonl")),
            "--docs",
            str(Path("tests/fixtures")),
            "--config",
            str(config),
            "--output",
            str(report_path),
            "--eval-data-dir",
            str(tmp_path / "eval-data"),
            "--min-mrr",
            "1.0",
            "--min-recall-at-k",
            "1.0",
            "--min-hit-at-k",
            "1.0",
            "--min-precision-at-k",
            "1.0",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "eval failed" in result.stdout
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"]["passed"] is False
    assert any(case["failures"] for case in report["cases"])


def _write_hashing_config(tmp_path: Path) -> Path:
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
model:
  provider: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
""",
        encoding="utf-8",
    )
    return config
