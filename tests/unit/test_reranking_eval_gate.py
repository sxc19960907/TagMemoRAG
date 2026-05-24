from __future__ import annotations

import json
from pathlib import Path
import sys

from tagmemorag.reranking_eval_gate import (
    SCHEMA_VERSION,
    run_reranking_eval_gate,
    write_reranking_eval_gate_report,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import reranking_eval_gate as gate_cli  # noqa: E402


def test_gate_passes_identical_reports(tmp_path):
    paths = _write_inputs(tmp_path)

    report = run_reranking_eval_gate(**paths)
    body = report.to_dict()

    assert body["schema_version"] == SCHEMA_VERSION
    assert body["status"] == "passed"
    assert all(check["status"] == "passed" for check in body["checks"])
    assert "actual_top_k" not in json.dumps(body, ensure_ascii=False)


def test_gate_fails_when_candidate_readiness_is_not_passed(tmp_path):
    paths = _write_inputs(tmp_path, candidate_readiness_status="warning")

    report = run_reranking_eval_gate(**paths)

    assert report.status == "failed"
    failed = {check.name for check in report.checks if check.status == "failed"}
    assert "release_readiness_status" in failed


def test_gate_fails_general_web_metric_decrease(tmp_path):
    paths = _write_inputs(tmp_path, candidate_mrr=0.7)

    report = run_reranking_eval_gate(**paths)

    assert report.status == "failed"
    failed = {check.name for check in report.checks if check.status == "failed"}
    assert "general_web_mrr" in failed


def test_gate_fails_pressure_count_increase(tmp_path):
    paths = _write_inputs(tmp_path, candidate_pressure_count=3)

    report = run_reranking_eval_gate(**paths)

    assert report.status == "failed"
    failed = {check.name for check in report.checks if check.status == "failed"}
    assert "ranking_pressure_count" in failed


def test_gate_fails_when_tracked_case_moves_later(tmp_path):
    paths = _write_inputs(tmp_path, candidate_repo_rank=7)

    report = run_reranking_eval_gate(**paths)

    assert report.status == "failed"
    failed = {check.name for check in report.checks if check.status == "failed"}
    assert "case_first_matched_rank:github-hello-world-repository" in failed


def test_output_omits_raw_queries_and_snippets(tmp_path):
    paths = _write_inputs(tmp_path, include_private_payload=True)

    serialized = run_reranking_eval_gate(**paths).to_json()

    assert "private query should not leak" not in serialized
    assert "raw snippet should not leak" not in serialized
    assert "actual_top_k" not in serialized


def test_write_markdown(tmp_path):
    paths = _write_inputs(tmp_path)
    report = run_reranking_eval_gate(**paths)
    output = tmp_path / "gate.md"

    write_reranking_eval_gate_report(report, output, fmt="markdown")

    text = output.read_text(encoding="utf-8")
    assert text.startswith("# Reranking Evaluation Gate")
    assert "| `general_web_mrr` | `passed` |" in text


def test_cli_returns_nonzero_for_failed_gate(tmp_path):
    paths = _write_inputs(tmp_path, candidate_mrr=0.7)
    output = tmp_path / "gate.json"

    exit_code = gate_cli.main(
        [
            "--baseline-readiness",
            str(paths["baseline_readiness_path"]),
            "--candidate-readiness",
            str(paths["candidate_readiness_path"]),
            "--baseline-ranking-pressure",
            str(paths["baseline_ranking_pressure_path"]),
            "--candidate-ranking-pressure",
            str(paths["candidate_ranking_pressure_path"]),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "failed"


def test_cli_returns_two_for_missing_input(tmp_path, capsys):
    paths = _write_inputs(tmp_path)

    exit_code = gate_cli.main(
        [
            "--baseline-readiness",
            str(tmp_path / "missing.json"),
            "--candidate-readiness",
            str(paths["candidate_readiness_path"]),
            "--baseline-ranking-pressure",
            str(paths["baseline_ranking_pressure_path"]),
            "--candidate-ranking-pressure",
            str(paths["candidate_ranking_pressure_path"]),
        ]
    )

    assert exit_code == 2
    assert "reranking-eval-gate error" in capsys.readouterr().err


def _write_inputs(
    tmp_path: Path,
    *,
    candidate_readiness_status: str = "passed",
    candidate_mrr: float = 0.77381,
    candidate_pressure_count: int = 2,
    candidate_repo_rank: int = 6,
    include_private_payload: bool = False,
) -> dict[str, str]:
    baseline_readiness = tmp_path / "baseline-readiness.json"
    candidate_readiness = tmp_path / "candidate-readiness.json"
    baseline_pressure = tmp_path / "baseline-pressure.json"
    candidate_pressure = tmp_path / "candidate-pressure.json"
    _write(
        baseline_readiness,
        _readiness(status="passed", mrr=0.77381),
    )
    _write(
        candidate_readiness,
        _readiness(status=candidate_readiness_status, mrr=candidate_mrr),
    )
    _write(
        baseline_pressure,
        _pressure(repo_rank=6, pressure_count=2, include_private_payload=include_private_payload),
    )
    _write(
        candidate_pressure,
        _pressure(
            repo_rank=candidate_repo_rank,
            pressure_count=candidate_pressure_count,
            include_private_payload=include_private_payload,
        ),
    )
    return {
        "baseline_readiness_path": str(baseline_readiness),
        "candidate_readiness_path": str(candidate_readiness),
        "baseline_ranking_pressure_path": str(baseline_pressure),
        "candidate_ranking_pressure_path": str(candidate_pressure),
    }


def _readiness(*, status: str, mrr: float) -> dict:
    return {
        "schema_version": "release_readiness.v1",
        "status": status,
        "stages": [
            {
                "name": "general_web_retrieval",
                "status": "passed",
                "detail": {
                    "cases": 7,
                    "hit_at_k": 1.0,
                    "recall_at_k": 0.971429,
                    "mrr": mrr,
                    "ranking_pressure_count": 2,
                    "highest_pressure_rank_count": 5,
                },
            }
        ],
        "next_steps": [],
    }


def _pressure(*, repo_rank: int, pressure_count: int, include_private_payload: bool = False) -> dict:
    items = [
        {
            "case_id": "github-hello-world-repository",
            "first_matched_rank": repo_rank,
            "pressure_rank_count": max(repo_rank - 1, 0),
            "metrics": {"mrr": round(1.0 / repo_rank, 6), "recall_at_k": 1.0, "hit_at_k": 1.0},
        },
        {
            "case_id": "github-hello-world-pull-request",
            "first_matched_rank": 4,
            "pressure_rank_count": 3,
            "metrics": {"mrr": 0.25, "recall_at_k": 1.0, "hit_at_k": 1.0},
        },
    ]
    if include_private_payload:
        items[0]["query"] = "private query should not leak"
        items[0]["top_results"] = [{"text": "raw snippet should not leak"}]
        items[0]["actual_top_k"] = [{"text": "raw snippet should not leak"}]
    return {
        "schema_version": "general_web_ranking_pressure.v1",
        "summary": {
            "cases": 7,
            "hit_at_k": 1.0,
            "recall_at_k": 0.971429,
            "mrr": 0.77381,
            "ranking_pressure_count": pressure_count,
            "highest_pressure_rank_count": 5,
        },
        "items": items,
    }


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
