from __future__ import annotations

import json
from pathlib import Path
import sys

from tagmemorag.reranking_gate_batch import SCHEMA_VERSION, run_reranking_gate_batch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import reranking_gate_batch as batch_cli  # noqa: E402


def test_batch_passes_and_writes_bounded_reports(tmp_path, monkeypatch):
    pressure = tmp_path / "pressure.json"
    readiness_paths = _reports(tmp_path)
    _write(pressure, _pressure())
    monkeypatch.setattr("tagmemorag.reranking_gate_batch.DEFAULT_REPORT_PATHS", readiness_paths)

    report = run_reranking_gate_batch(
        output_dir=tmp_path / "out",
        general_web_ranking_pressure_path=pressure,
    )
    body = report.to_dict()

    assert body["schema_version"] == SCHEMA_VERSION
    assert body["status"] == "passed"
    assert body["release_readiness_status"] == "passed"
    assert body["reranking_gate_status"] == "passed"
    assert (tmp_path / "out" / "release-readiness.json").exists()
    assert (tmp_path / "out" / "reranking-gate.json").exists()
    assert (tmp_path / "out" / "batch-summary.json").exists()
    serialized = json.dumps(body, ensure_ascii=False)
    assert "actual_top_k" not in serialized
    assert "raw snippet should not leak" not in serialized


def test_batch_fails_when_candidate_gate_fails(tmp_path, monkeypatch):
    baseline_pressure = tmp_path / "baseline-pressure.json"
    candidate_pressure = tmp_path / "candidate-pressure.json"
    readiness_paths = _reports(tmp_path)
    _write(baseline_pressure, _pressure(repo_rank=6, pressure_count=2))
    _write(candidate_pressure, _pressure(repo_rank=7, pressure_count=3))
    monkeypatch.setattr("tagmemorag.reranking_gate_batch.DEFAULT_REPORT_PATHS", readiness_paths)

    report = run_reranking_gate_batch(
        output_dir=tmp_path / "out",
        general_web_ranking_pressure_path=baseline_pressure,
        baseline_ranking_pressure_path=baseline_pressure,
        candidate_ranking_pressure_path=candidate_pressure,
    )

    assert report.status == "failed"
    assert report.reranking_gate_status == "failed"
    assert "ranking_pressure_count" in report.failed_checks
    assert "case_first_matched_rank:github-hello-world-repository" in report.failed_checks


def test_batch_derives_candidate_pressure_from_eval_report(tmp_path, monkeypatch):
    baseline_pressure = tmp_path / "baseline-pressure.json"
    candidate_eval = tmp_path / "candidate-eval.json"
    readiness_paths = _reports(tmp_path)
    _write(baseline_pressure, _pressure(repo_rank=6, pressure_count=2))
    _write(candidate_eval, _eval_report(first_rank=1))
    monkeypatch.setattr("tagmemorag.reranking_gate_batch.DEFAULT_REPORT_PATHS", readiness_paths)

    report = run_reranking_gate_batch(
        output_dir=tmp_path / "out",
        general_web_ranking_pressure_path=baseline_pressure,
        baseline_ranking_pressure_path=baseline_pressure,
        candidate_eval_report_path=candidate_eval,
    )

    candidate_pressure = tmp_path / "out" / "candidate-ranking-pressure.json"
    assert report.status == "passed"
    assert report.reports["candidate_ranking_pressure"] == str(candidate_pressure)
    body = json.loads(candidate_pressure.read_text(encoding="utf-8"))
    assert body["summary"]["ranking_pressure_count"] == 0
    serialized = json.dumps(body, ensure_ascii=False)
    assert "private query should not leak" not in serialized
    assert "raw snippet should not leak" not in serialized
    assert "actual_top_k" not in serialized


def test_batch_prefers_explicit_candidate_pressure_over_eval_report(tmp_path, monkeypatch):
    baseline_pressure = tmp_path / "baseline-pressure.json"
    candidate_pressure = tmp_path / "candidate-pressure.json"
    candidate_eval = tmp_path / "candidate-eval.json"
    readiness_paths = _reports(tmp_path)
    _write(baseline_pressure, _pressure(repo_rank=6, pressure_count=2))
    _write(candidate_pressure, _pressure(repo_rank=6, pressure_count=2))
    _write(candidate_eval, _eval_report(first_rank=7))
    monkeypatch.setattr("tagmemorag.reranking_gate_batch.DEFAULT_REPORT_PATHS", readiness_paths)

    report = run_reranking_gate_batch(
        output_dir=tmp_path / "out",
        general_web_ranking_pressure_path=baseline_pressure,
        baseline_ranking_pressure_path=baseline_pressure,
        candidate_ranking_pressure_path=candidate_pressure,
        candidate_eval_report_path=candidate_eval,
    )

    assert report.status == "passed"
    assert report.reports["candidate_ranking_pressure"] == str(candidate_pressure)
    assert not (tmp_path / "out" / "candidate-ranking-pressure.json").exists()


def test_batch_markdown_summary(tmp_path, monkeypatch):
    pressure = tmp_path / "pressure.json"
    readiness_paths = _reports(tmp_path)
    _write(pressure, _pressure())
    monkeypatch.setattr("tagmemorag.reranking_gate_batch.DEFAULT_REPORT_PATHS", readiness_paths)

    report = run_reranking_gate_batch(
        output_dir=tmp_path / "out",
        general_web_ranking_pressure_path=pressure,
        summary_format="markdown",
    )

    text = (tmp_path / "out" / "batch-summary.md").read_text(encoding="utf-8")
    assert report.status == "passed"
    assert text.startswith("# Reranking Gate Batch")


def test_cli_returns_zero_for_passing_batch(tmp_path, monkeypatch):
    pressure = tmp_path / "pressure.json"
    readiness_paths = _reports(tmp_path)
    _write(pressure, _pressure())
    monkeypatch.setattr("tagmemorag.reranking_gate_batch.DEFAULT_REPORT_PATHS", readiness_paths)

    exit_code = batch_cli.main(
        [
            "--output-dir",
            str(tmp_path / "out"),
            "--general-web-ranking-pressure",
            str(pressure),
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "out" / "batch-summary.json").exists()


def test_cli_accepts_candidate_eval_report(tmp_path, monkeypatch):
    pressure = tmp_path / "pressure.json"
    candidate_eval = tmp_path / "candidate-eval.json"
    readiness_paths = _reports(tmp_path)
    _write(pressure, _pressure(repo_rank=6, pressure_count=2))
    _write(candidate_eval, _eval_report(first_rank=1))
    monkeypatch.setattr("tagmemorag.reranking_gate_batch.DEFAULT_REPORT_PATHS", readiness_paths)

    exit_code = batch_cli.main(
        [
            "--output-dir",
            str(tmp_path / "out"),
            "--general-web-ranking-pressure",
            str(pressure),
            "--baseline-ranking-pressure",
            str(pressure),
            "--candidate-eval-report",
            str(candidate_eval),
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "out" / "candidate-ranking-pressure.json").exists()


def test_cli_returns_two_for_missing_pressure(tmp_path, capsys):
    exit_code = batch_cli.main(
        [
            "--output-dir",
            str(tmp_path / "out"),
            "--general-web-ranking-pressure",
            str(tmp_path / "missing.json"),
        ]
    )

    assert exit_code == 2
    assert "reranking-gate-batch error" in capsys.readouterr().err


def _pressure(*, repo_rank: int = 6, pressure_count: int = 2) -> dict:
    return {
        "schema_version": "general_web_ranking_pressure.v1",
        "summary": {
            "cases": 7,
            "hit_at_k": 1.0,
            "recall_at_k": 0.971429,
            "mrr": 0.77381,
            "ranking_pressure_count": pressure_count,
            "highest_pressure_rank_count": max(repo_rank - 1, 5),
        },
        "items": [
            {
                "case_id": "github-hello-world-repository",
                "first_matched_rank": repo_rank,
                "pressure_rank_count": max(repo_rank - 1, 0),
                "query": "private query should not leak",
                "top_results": [{"text": "raw snippet should not leak"}],
                "actual_top_k": [{"text": "raw snippet should not leak"}],
            },
            {
                "case_id": "github-hello-world-pull-request",
                "first_matched_rank": 4,
                "pressure_rank_count": 3,
            },
        ],
    }


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")


def _reports(tmp_path: Path) -> dict[str, str]:
    paths = {}
    for name in (
        "general_web_retrieval",
        "multiformat_retrieval",
        "mixed_domain_retrieval",
        "realmanuals_retrieval",
        "general_web_context",
        "general_web_context_tight",
        "multiformat_context",
        "multiformat_context_tight",
        "general_web_answer",
        "multiformat_answer",
        "product_qa_answer_quality",
        "general_web_ranking_pressure",
    ):
        paths[name] = str(tmp_path / f"{name}.json")
    for name in ("general_web_retrieval", "multiformat_retrieval", "mixed_domain_retrieval", "realmanuals_retrieval"):
        _write(
            tmp_path / f"{name}.json",
            {"summary": {"cases": 3, "hit_at_k": 1.0, "recall_at_k": 1.0, "mrr": 1.0}},
        )
    for name in ("general_web_context", "general_web_context_tight", "multiformat_context", "multiformat_context_tight"):
        _write(
            tmp_path / f"{name}.json",
            {
                "summary": {
                    "cases": 3,
                    "cases_with_expected_retrieved": 3,
                    "cases_with_expected_selected": 3,
                    "selected_expected_rate": 1.0,
                },
            },
        )
    for name in ("general_web_answer", "multiformat_answer"):
        _write(tmp_path / f"{name}.json", {"summary": {"cases": 3, "failed": 0, "passed": True}})
    _write(
        tmp_path / "product_qa_answer_quality.json",
        {
            "summary": {
                "cases": 2,
                "passed": True,
                "dimensions": {
                    "grounded": {"passed": 2, "failed": 0},
                    "relevant": {"passed": 2, "failed": 0},
                },
            },
        },
    )
    return paths


def _eval_report(*, first_rank: int) -> dict:
    actual_top_k = []
    for rank in range(1, max(first_rank, 1) + 1):
        actual_top_k.append(
            {
                "text": "raw snippet should not leak",
                "header": "GitHub Docs",
                "source_file": "github.md",
                "matched_expected_indexes": [0] if rank == first_rank else [],
            }
        )
    return {
        "suite": "tests/fixtures/eval/general_web.jsonl",
        "summary": {
            "cases": 1,
            "passed": True,
            "precision_at_k": 0.2,
            "recall_at_k": 1.0,
            "mrr": 1.0 if first_rank == 1 else 1 / first_rank,
            "hit_at_k": 1.0,
        },
        "cases": [
            {
                "id": "github-hello-world-repository",
                "kb_name": "general_web",
                "query": "private query should not leak",
                "expected": ["expected fixture text"],
                "metrics": {
                    "precision_at_k": 0.2,
                    "recall_at_k": 1.0,
                    "mrr": 1.0 if first_rank == 1 else 1 / first_rank,
                    "hit_at_k": 1.0,
                },
                "actual_top_k": actual_top_k,
            }
        ],
    }
