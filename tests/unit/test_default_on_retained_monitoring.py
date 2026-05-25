from __future__ import annotations

import json
from pathlib import Path
import sys

from tagmemorag.default_on_retained_monitoring import (
    MANIFEST_SCHEMA_VERSION,
    run_default_on_retained_monitoring,
    write_monitoring_report,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import default_on_retained_monitoring as monitoring_cli  # noqa: E402


def test_monitoring_passes_and_omits_case_payloads(tmp_path):
    manifest = _write_manifest(tmp_path)

    report = run_default_on_retained_monitoring(manifest)
    body = report.to_dict()

    assert body["status"] == "passed"
    assert body["slices"][0]["cases"] == 7
    assert body["gates"][0]["status"] == "passed"
    serialized = json.dumps(body, ensure_ascii=False)
    assert "private query should not leak" not in serialized
    assert "raw snippet should not leak" not in serialized
    assert "actual_top_k" not in serialized


def test_monitoring_fails_missing_report(tmp_path):
    manifest = _write_manifest(tmp_path, report_path=tmp_path / "missing.json")

    report = run_default_on_retained_monitoring(manifest)

    assert report.status == "failed"
    assert "slice:general_web:report_read" in report.failed_checks


def test_monitoring_fails_threshold_regression(tmp_path):
    manifest = _write_manifest(tmp_path, mrr=0.5)

    report = run_default_on_retained_monitoring(manifest)

    assert report.status == "failed"
    assert "slice:general_web:mrr" in report.failed_checks


def test_monitoring_fails_gate_regression(tmp_path):
    manifest = _write_manifest(tmp_path, gate_status="failed")

    report = run_default_on_retained_monitoring(manifest)

    assert report.status == "failed"
    assert "gate:release_readiness:failed" in report.failed_checks


def test_monitoring_markdown_output(tmp_path):
    manifest = _write_manifest(tmp_path)
    report = run_default_on_retained_monitoring(manifest)
    output = tmp_path / "summary.md"

    write_monitoring_report(report, output, fmt="markdown")

    text = output.read_text(encoding="utf-8")
    assert text.startswith("# Default-On Retained Monitoring")
    assert "| `general_web` | `passed` | 7 |" in text


def test_monitoring_cli_writes_output(tmp_path):
    manifest = _write_manifest(tmp_path)
    output = tmp_path / "summary.json"

    exit_code = monitoring_cli.main(["--manifest", str(manifest), "--output", str(output)])

    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "passed"


def _write_manifest(
    tmp_path: Path,
    *,
    report_path: Path | None = None,
    mrr: float = 1.0,
    gate_status: str = "passed",
) -> Path:
    report = report_path or tmp_path / "general-web.json"
    if report_path is None:
        report.write_text(json.dumps(_eval_report(mrr=mrr), ensure_ascii=False), encoding="utf-8")
    gate = tmp_path / "release-readiness.json"
    gate.write_text(json.dumps({"status": gate_status}, ensure_ascii=False), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "slices": [
                    {
                        "name": "general_web",
                        "kind": "retrieval",
                        "suite_path": "tests/fixtures/eval/general_web.jsonl",
                        "corpus_path": ".tmp/general-web-eval/general_web",
                        "rerun_command": None,
                        "report_path": str(report),
                        "min_hit_at_k": 1.0,
                        "min_recall_at_k": 0.9,
                        "min_mrr": 0.95,
                    }
                ],
                "gates": [{"name": "release_readiness", "path": str(gate)}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return manifest


def _eval_report(*, mrr: float) -> dict:
    return {
        "summary": {
            "cases": 7,
            "passed": True,
            "hit_at_k": 1.0,
            "recall_at_k": 0.971429,
            "mrr": mrr,
        },
        "cases": [
            {
                "id": "private-case",
                "query": "private query should not leak",
                "actual_top_k": [{"text": "raw snippet should not leak"}],
            }
        ],
    }
