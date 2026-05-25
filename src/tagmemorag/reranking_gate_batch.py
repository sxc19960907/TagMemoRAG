from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .general_web_ranking_pressure import summarize_ranking_pressure, write_report as write_ranking_pressure_report
from .release_readiness import DEFAULT_REPORT_PATHS, run_release_readiness, write_release_readiness_report
from .reranking_eval_gate import (
    RerankingEvalGateReport,
    run_reranking_eval_gate,
    write_reranking_eval_gate_report,
)


SCHEMA_VERSION = "reranking_gate_batch.v1"


@dataclass(frozen=True)
class RerankingGateBatchReport:
    status: str
    release_readiness_status: str
    reranking_gate_status: str
    reports: dict[str, str]
    failed_checks: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "release_readiness_status": self.release_readiness_status,
            "reranking_gate_status": self.reranking_gate_status,
            "reports": dict(self.reports),
            "failed_checks": list(self.failed_checks),
            "next_steps": list(self.next_steps),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            "# Reranking Gate Batch",
            "",
            f"- Status: `{self.status}`",
            f"- Release readiness: `{self.release_readiness_status}`",
            f"- Reranking gate: `{self.reranking_gate_status}`",
            "",
            "## Reports",
        ]
        lines.extend(f"- `{name}`: `{path}`" for name, path in sorted(self.reports.items()))
        if self.failed_checks:
            lines.extend(["", "## Failed Checks"])
            lines.extend(f"- `{check}`" for check in self.failed_checks)
        if self.next_steps:
            lines.extend(["", "## Next Steps"])
            lines.extend(f"- {step}" for step in self.next_steps)
        return "\n".join(lines) + "\n"


def run_reranking_gate_batch(
    *,
    output_dir: str | Path,
    general_web_ranking_pressure_path: str | Path = DEFAULT_REPORT_PATHS["general_web_ranking_pressure"],
    baseline_readiness_path: str | Path | None = None,
    candidate_readiness_path: str | Path | None = None,
    baseline_ranking_pressure_path: str | Path | None = None,
    candidate_ranking_pressure_path: str | Path | None = None,
    candidate_eval_report_path: str | Path | None = None,
    summary_format: str = "json",
) -> RerankingGateBatchReport:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    readiness_path = output_root / "release-readiness.json"
    gate_path = output_root / "reranking-gate.json"
    summary_path = output_root / ("batch-summary.md" if summary_format == "markdown" else "batch-summary.json")

    paths = dict(DEFAULT_REPORT_PATHS)
    paths["general_web_ranking_pressure"] = str(general_web_ranking_pressure_path)
    readiness = run_release_readiness(report_paths=paths)
    write_release_readiness_report(readiness, readiness_path, fmt="json")

    baseline_readiness = Path(baseline_readiness_path) if baseline_readiness_path is not None else readiness_path
    candidate_readiness = Path(candidate_readiness_path) if candidate_readiness_path is not None else readiness_path
    baseline_pressure = (
        Path(baseline_ranking_pressure_path)
        if baseline_ranking_pressure_path is not None
        else Path(general_web_ranking_pressure_path)
    )
    candidate_pressure = _candidate_pressure_path(
        output_root=output_root,
        general_web_ranking_pressure_path=general_web_ranking_pressure_path,
        candidate_ranking_pressure_path=candidate_ranking_pressure_path,
        candidate_eval_report_path=candidate_eval_report_path,
    )
    gate = run_reranking_eval_gate(
        baseline_readiness_path=baseline_readiness,
        candidate_readiness_path=candidate_readiness,
        baseline_ranking_pressure_path=baseline_pressure,
        candidate_ranking_pressure_path=candidate_pressure,
    )
    write_reranking_eval_gate_report(gate, gate_path, fmt="json")

    report = _batch_report(
        readiness.status,
        gate,
        readiness_path,
        gate_path,
        summary_path,
        candidate_pressure_path=candidate_pressure if candidate_pressure != Path(general_web_ranking_pressure_path) else None,
    )
    write_reranking_gate_batch_report(report, summary_path, fmt=summary_format)
    return report


def write_reranking_gate_batch_report(report: RerankingGateBatchReport, path: str | Path, *, fmt: str = "json") -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        text = report.to_json()
    elif fmt == "markdown":
        text = report.to_markdown()
    else:
        raise ValueError("fmt must be 'json' or 'markdown'")
    output_path.write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")


def _batch_report(
    readiness_status: str,
    gate: RerankingEvalGateReport,
    readiness_path: Path,
    gate_path: Path,
    summary_path: Path,
    candidate_pressure_path: Path | None = None,
) -> RerankingGateBatchReport:
    failed_checks = [check.name for check in gate.checks if check.status != "passed"]
    status = "passed" if readiness_status == "passed" and gate.status == "passed" else "failed"
    next_steps = (
        ["Baseline batch gates are green; continue with the next stability-program child task."]
        if status == "passed"
        else ["Do not proceed to candidate ranking work until failed batch gates are addressed."]
    )
    reports = {
        "release_readiness": str(readiness_path),
        "reranking_gate": str(gate_path),
        "summary": str(summary_path),
    }
    if candidate_pressure_path is not None:
        reports["candidate_ranking_pressure"] = str(candidate_pressure_path)
    return RerankingGateBatchReport(
        status=status,
        release_readiness_status=readiness_status,
        reranking_gate_status=gate.status,
        reports=reports,
        failed_checks=failed_checks,
        next_steps=next_steps,
    )


def _candidate_pressure_path(
    *,
    output_root: Path,
    general_web_ranking_pressure_path: str | Path,
    candidate_ranking_pressure_path: str | Path | None,
    candidate_eval_report_path: str | Path | None,
) -> Path:
    if candidate_ranking_pressure_path is not None:
        return Path(candidate_ranking_pressure_path)
    if candidate_eval_report_path is None:
        return Path(general_web_ranking_pressure_path)
    candidate_pressure = output_root / "candidate-ranking-pressure.json"
    pressure_report = summarize_ranking_pressure(candidate_eval_report_path)
    write_ranking_pressure_report(pressure_report, candidate_pressure, fmt="json")
    return candidate_pressure
