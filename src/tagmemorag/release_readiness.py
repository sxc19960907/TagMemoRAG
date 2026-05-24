from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping


RELEASE_READINESS_SCHEMA_VERSION = "release_readiness.v1"

DEFAULT_REPORT_PATHS = {
    "general_web_retrieval": ".tmp/eval/general-web-after-evidence-prior.json",
    "general_web_ranking_pressure": ".tmp/eval/general-web-ranking-pressure.json",
    "multiformat_retrieval": ".tmp/eval/multiformat-after-fit-compaction.json",
    "mixed_domain_retrieval": ".tmp/eval/mixed-domain-after-evidence-prior.json",
    "realmanuals_retrieval": ".tmp/eval/realmanuals-after-evidence-prior.json",
    "general_web_context": ".tmp/eval/context-quality-general-web-after-adjacent-merge.json",
    "general_web_context_tight": ".tmp/eval/context-quality-general-web-budget260-after-adjacent-merge.json",
    "multiformat_context": ".tmp/eval/context-quality-multiformat-after-adjacent-merge.json",
    "multiformat_context_tight": ".tmp/eval/context-quality-multiformat-budget260-after-fit-compaction.json",
    "general_web_answer": ".tmp/eval/general-web-answer-after-evidence-prior.json",
    "multiformat_answer": ".tmp/eval/multiformat-answer-after-fit-compaction.json",
    "product_qa_answer_quality": ".tmp/eval/product-qa-answer-quality-after-evidence-prior.json",
}

RETRIEVAL_GATES = {
    "general_web_retrieval": {"min_hit_at_k": 1.0, "min_recall_at_k": 0.9, "warn_mrr_below": 0.75},
    "multiformat_retrieval": {"min_hit_at_k": 1.0, "min_recall_at_k": 1.0, "warn_mrr_below": 0.75},
    "mixed_domain_retrieval": {"min_hit_at_k": 1.0, "min_recall_at_k": 1.0, "warn_mrr_below": 0.95},
    "realmanuals_retrieval": {"min_hit_at_k": 1.0, "min_recall_at_k": 0.95, "warn_mrr_below": 0.75},
}

CONTEXT_GATES = {
    "general_web_context": {"min_selected_expected_rate": 1.0},
    "general_web_context_tight": {"min_selected_expected_rate": 1.0},
    "multiformat_context": {"min_selected_expected_rate": 1.0},
    "multiformat_context_tight": {"min_selected_expected_rate": 2 / 3, "warn_selected_expected_below": 1.0},
}


@dataclass(frozen=True)
class ReleaseReadinessStage:
    name: str
    status: str
    detail: dict[str, Any] = field(default_factory=dict)
    risks: list[str] = field(default_factory=list)
    error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "detail": dict(self.detail),
        }
        if self.risks:
            payload["risks"] = list(self.risks)
        if self.error is not None:
            payload["error"] = dict(self.error)
        return payload


@dataclass(frozen=True)
class ReleaseReadinessReport:
    status: str
    stages: list[ReleaseReadinessStage]
    next_steps: list[str]
    report_paths: dict[str, str]
    schema_version: str = RELEASE_READINESS_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "report_paths": dict(self.report_paths),
            "stages": [stage.to_dict() for stage in self.stages],
            "next_steps": list(self.next_steps),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            "# TagMemoRAG Release Readiness Report",
            "",
            f"- Status: `{self.status}`",
            "",
            "| Stage | Status | Detail | Risks |",
            "| --- | --- | --- | --- |",
        ]
        for stage in self.stages:
            detail = _compact_detail(stage.detail)
            risks = "<br>".join(stage.risks)
            if stage.error:
                risks = f"{risks}<br>error={stage.error.get('type', 'Error')}:{stage.error.get('reason', '')}".strip("<br>")
            lines.append(f"| `{stage.name}` | `{stage.status}` | {detail} | {risks} |")
        if self.next_steps:
            lines.extend(["", "## Next Steps"])
            lines.extend(f"- {step}" for step in self.next_steps)
        return "\n".join(lines) + "\n"


def run_release_readiness(*, report_paths: Mapping[str, str | Path] | None = None) -> ReleaseReadinessReport:
    paths = {key: str(value) for key, value in (report_paths or DEFAULT_REPORT_PATHS).items()}
    optional = _optional_ranking_pressure(paths.get("general_web_ranking_pressure", ""))
    stages: list[ReleaseReadinessStage] = []
    for name in ("general_web_retrieval", "multiformat_retrieval", "mixed_domain_retrieval", "realmanuals_retrieval"):
        stages.append(_retrieval_stage(name, paths.get(name, ""), optional if name == "general_web_retrieval" else {}))
    for name in ("general_web_context", "general_web_context_tight", "multiformat_context", "multiformat_context_tight"):
        stages.append(_context_stage(name, paths.get(name, "")))
    for name in ("general_web_answer", "multiformat_answer", "product_qa_answer_quality"):
        stages.append(_answer_stage(name, paths.get(name, "")))
    status = _aggregate_status(stages)
    return ReleaseReadinessReport(
        status=status,
        stages=stages,
        next_steps=_next_steps(status, stages, optional),
        report_paths=paths,
    )


def write_release_readiness_report(report: ReleaseReadinessReport, path: str | Path, *, fmt: str = "json") -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        text = report.to_json()
    elif fmt == "markdown":
        text = report.to_markdown()
    else:
        raise ValueError("fmt must be 'json' or 'markdown'")
    output_path.write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")


def _retrieval_stage(name: str, path: str, optional_detail: dict[str, Any] | None = None) -> ReleaseReadinessStage:
    data, error = _read_json(path)
    if error is not None:
        return ReleaseReadinessStage(name, "failed", {"path": path}, error=error)
    summary = dict(data.get("summary") or {})
    gates = RETRIEVAL_GATES[name]
    detail = {
        "cases": int(summary.get("cases") or 0),
        "hit_at_k": round(float(summary.get("hit_at_k") or 0.0), 6),
        "recall_at_k": round(float(summary.get("recall_at_k") or 0.0), 6),
        "mrr": round(float(summary.get("mrr") or 0.0), 6),
    }
    if optional_detail:
        detail.update(optional_detail)
    failures = []
    risks = []
    if detail["hit_at_k"] < gates["min_hit_at_k"]:
        failures.append(f"hit@k {detail['hit_at_k']:.6f} < {gates['min_hit_at_k']:.6f}")
    if detail["recall_at_k"] < gates["min_recall_at_k"]:
        failures.append(f"recall@k {detail['recall_at_k']:.6f} < {gates['min_recall_at_k']:.6f}")
    if detail["mrr"] < gates["warn_mrr_below"]:
        risks.append(f"MRR below release target: {detail['mrr']:.6f} < {gates['warn_mrr_below']:.6f}")
    status = "failed" if failures else "warning" if risks else "passed"
    return ReleaseReadinessStage(name, status, detail, failures + risks)


def _context_stage(name: str, path: str) -> ReleaseReadinessStage:
    data, error = _read_json(path)
    if error is not None:
        return ReleaseReadinessStage(name, "failed", {"path": path}, error=error)
    summary = dict(data.get("summary") or {})
    gates = CONTEXT_GATES[name]
    rate = float(summary.get("selected_expected_rate") or 0.0)
    detail = {
        "cases": int(summary.get("cases") or 0),
        "cases_with_expected_retrieved": int(summary.get("cases_with_expected_retrieved") or 0),
        "cases_with_expected_selected": int(summary.get("cases_with_expected_selected") or 0),
        "selected_expected_rate": round(rate, 6),
    }
    failures = []
    risks = []
    if rate + 1e-9 < gates["min_selected_expected_rate"]:
        failures.append(f"selected expected rate {rate:.6f} < {gates['min_selected_expected_rate']:.6f}")
    warn_below = gates.get("warn_selected_expected_below")
    if warn_below is not None and rate + 1e-9 < warn_below:
        risks.append(f"tight-budget context is not complete: {rate:.6f} < {warn_below:.6f}")
    status = "failed" if failures else "warning" if risks else "passed"
    return ReleaseReadinessStage(name, status, detail, failures + risks)


def _answer_stage(name: str, path: str) -> ReleaseReadinessStage:
    data, error = _read_json(path)
    if error is not None:
        return ReleaseReadinessStage(name, "failed", {"path": path}, error=error)
    summary = dict(data.get("summary") or {})
    if name == "product_qa_answer_quality":
        passed = bool(summary.get("passed"))
        failed = sum(int(value.get("failed") or 0) for value in dict(summary.get("dimensions") or {}).values())
        detail = {"cases": int(summary.get("cases") or 0), "failed_dimension_checks": failed}
    else:
        failed = int(summary.get("failed") or 0)
        passed = bool(summary.get("passed")) and failed == 0
        detail = {"cases": int(summary.get("cases") or 0), "failed": failed}
    risks = [] if passed else [f"answer quality failures: {failed}"]
    return ReleaseReadinessStage(name, "passed" if passed else "failed", detail, risks)


def _read_json(path: str) -> tuple[dict[str, Any], dict[str, str] | None]:
    if not path:
        return {}, {"type": "MissingReportPath", "reason": "report_path_not_configured"}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except OSError as exc:
        return {}, {"type": "ReportReadError", "reason": _safe_reason(str(exc))}
    except json.JSONDecodeError as exc:
        return {}, {"type": "ReportJsonError", "reason": _safe_reason(exc.msg)}


def _aggregate_status(stages: list[ReleaseReadinessStage]) -> str:
    statuses = {stage.status for stage in stages}
    if "failed" in statuses:
        return "failed"
    if "warning" in statuses:
        return "warning"
    return "passed"


def _next_steps(status: str, stages: list[ReleaseReadinessStage], ranking_pressure: dict[str, Any] | None = None) -> list[str]:
    failed = [stage.name for stage in stages if stage.status == "failed"]
    warning = [stage.name for stage in stages if stage.status == "warning"]
    if status == "failed":
        return [
            "Regenerate or fix failed readiness report inputs: " + ", ".join(failed) + ".",
            "Do not treat this branch as release-ready until failed gates are green.",
        ]
    if status == "warning":
        steps = [
            "Review warning stages before release signoff: " + ", ".join(warning) + ".",
            "Keep this report with the release record and rerun it after the next quality batch.",
        ]
        if any(name.endswith("_retrieval") for name in warning):
            steps.insert(1, "Prioritize MRR/ranking improvements for warning retrieval stages.")
        if any(name.endswith("_context_tight") for name in warning):
            steps.insert(1, "Prioritize remaining tight-budget context completeness gaps.")
        return steps
    steps = [
        "Retain this report with the release record.",
        "Run live provider and deployment environment checks for the target release profile.",
    ]
    if ranking_pressure and int(ranking_pressure.get("ranking_pressure_count") or 0) > 0:
        steps.append(
            "Track non-blocking general-web ranking pressure before the next retrieval-quality batch: "
            f"{int(ranking_pressure.get('ranking_pressure_count') or 0)} case(s), "
            f"highest pressure ranks={int(ranking_pressure.get('highest_pressure_rank_count') or 0)}."
        )
    return steps


def _optional_ranking_pressure(path: str) -> dict[str, Any]:
    data, error = _read_optional_json(path)
    if error is not None:
        return {}
    if not isinstance(data, dict):
        return {}
    raw_summary = data.get("summary")
    if not isinstance(raw_summary, dict):
        return {}
    summary = dict(raw_summary)
    count = int(summary.get("ranking_pressure_count") or 0)
    if count <= 0:
        return {}
    return {
        "ranking_pressure_count": count,
        "highest_pressure_rank_count": int(summary.get("highest_pressure_rank_count") or 0),
    }


def _read_optional_json(path: str) -> tuple[dict[str, Any], dict[str, str] | None]:
    if not path:
        return {}, {"type": "MissingOptionalReportPath", "reason": "optional_report_path_not_configured"}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError):
        return {}, {"type": "OptionalReportReadError", "reason": "optional_report_unavailable"}


def _compact_detail(detail: dict[str, Any]) -> str:
    parts = []
    for key, value in detail.items():
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, dict) else str(value)
        parts.append(f"{key}={rendered}")
    return "<br>".join(parts)


def _safe_reason(reason: str) -> str:
    value = " ".join(str(reason or "").split())
    return value[:160] or "release_readiness_failed"
