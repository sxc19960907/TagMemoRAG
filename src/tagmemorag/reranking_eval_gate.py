from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "reranking_eval_gate.v1"
TRACKED_METRICS = ("hit_at_k", "recall_at_k", "mrr")


@dataclass(frozen=True)
class GateCheck:
    name: str
    status: str
    baseline: Any
    candidate: Any
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "baseline": self.baseline,
            "candidate": self.candidate,
            "message": self.message,
        }


@dataclass(frozen=True)
class RerankingEvalGateReport:
    status: str
    checks: list[GateCheck]
    summary: dict[str, Any] = field(default_factory=dict)
    next_steps: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "summary": dict(self.summary),
            "checks": [check.to_dict() for check in self.checks],
            "next_steps": list(self.next_steps),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            "# Reranking Evaluation Gate",
            "",
            f"- Status: `{self.status}`",
            "",
            "| Check | Status | Baseline | Candidate | Message |",
            "| --- | --- | ---: | ---: | --- |",
        ]
        for check in self.checks:
            lines.append(
                f"| `{check.name}` | `{check.status}` | "
                f"{_render_value(check.baseline)} | {_render_value(check.candidate)} | {check.message} |"
            )
        if self.next_steps:
            lines.extend(["", "## Next Steps"])
            lines.extend(f"- {step}" for step in self.next_steps)
        return "\n".join(lines) + "\n"


class RerankingEvalGateInputError(ValueError):
    """Raised when gate inputs cannot be read or interpreted."""


def run_reranking_eval_gate(
    *,
    baseline_readiness_path: str | Path,
    candidate_readiness_path: str | Path,
    baseline_ranking_pressure_path: str | Path,
    candidate_ranking_pressure_path: str | Path,
) -> RerankingEvalGateReport:
    baseline_readiness = _load_json(baseline_readiness_path)
    candidate_readiness = _load_json(candidate_readiness_path)
    baseline_pressure = _load_json(baseline_ranking_pressure_path)
    candidate_pressure = _load_json(candidate_ranking_pressure_path)

    baseline_general = _stage_detail(baseline_readiness, "general_web_retrieval")
    candidate_general = _stage_detail(candidate_readiness, "general_web_retrieval")
    baseline_pressure_summary = _summary(baseline_pressure)
    candidate_pressure_summary = _summary(candidate_pressure)

    checks: list[GateCheck] = [
        _check_readiness(candidate_readiness),
        *[
            _check_not_decreased(f"general_web_{metric}", baseline_general.get(metric), candidate_general.get(metric))
            for metric in TRACKED_METRICS
        ],
        _check_not_increased(
            "ranking_pressure_count",
            baseline_pressure_summary.get("ranking_pressure_count"),
            candidate_pressure_summary.get("ranking_pressure_count"),
        ),
        _check_not_increased(
            "highest_pressure_rank_count",
            baseline_pressure_summary.get("highest_pressure_rank_count"),
            candidate_pressure_summary.get("highest_pressure_rank_count"),
        ),
        *_new_pressure_case_checks(baseline_pressure, candidate_pressure),
        *_case_rank_checks(baseline_pressure, candidate_pressure),
    ]
    status = "failed" if any(check.status == "failed" for check in checks) else "passed"
    return RerankingEvalGateReport(
        status=status,
        checks=checks,
        summary={
            "baseline": _bounded_summary(baseline_readiness, baseline_pressure),
            "candidate": _bounded_summary(candidate_readiness, candidate_pressure),
        },
        next_steps=_next_steps(checks),
    )


def write_reranking_eval_gate_report(report: RerankingEvalGateReport, path: str | Path, *, fmt: str = "json") -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        text = report.to_json()
    elif fmt == "markdown":
        text = report.to_markdown()
    else:
        raise ValueError("fmt must be 'json' or 'markdown'")
    output_path.write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")


def _load_json(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise RerankingEvalGateInputError(f"could not read report: {_safe_reason(str(exc))}") from exc
    except json.JSONDecodeError as exc:
        raise RerankingEvalGateInputError(f"invalid report JSON: {_safe_reason(exc.msg)}") from exc
    if not isinstance(data, dict):
        raise RerankingEvalGateInputError("report root must be a JSON object")
    return data


def _stage_detail(readiness: dict[str, Any], name: str) -> dict[str, Any]:
    stages = readiness.get("stages")
    if not isinstance(stages, list):
        raise RerankingEvalGateInputError("release readiness report is missing stages")
    for stage in stages:
        if isinstance(stage, dict) and stage.get("name") == name:
            detail = stage.get("detail")
            if isinstance(detail, dict):
                return detail
            return {}
    raise RerankingEvalGateInputError(f"release readiness report is missing stage {name!r}")


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise RerankingEvalGateInputError("ranking pressure report is missing summary")
    return summary


def _check_readiness(candidate_readiness: dict[str, Any]) -> GateCheck:
    candidate = str(candidate_readiness.get("status") or "")
    status = "passed" if candidate == "passed" else "failed"
    return GateCheck(
        name="release_readiness_status",
        status=status,
        baseline="passed",
        candidate=candidate or "missing",
        message="candidate release readiness must remain passed",
    )


def _check_not_decreased(name: str, baseline: Any, candidate: Any) -> GateCheck:
    base = _as_float(baseline)
    cand = _as_float(candidate)
    status = "passed" if cand + 1e-9 >= base else "failed"
    return GateCheck(
        name=name,
        status=status,
        baseline=round(base, 6),
        candidate=round(cand, 6),
        message="candidate metric must not decrease",
    )


def _check_not_increased(name: str, baseline: Any, candidate: Any) -> GateCheck:
    base = _as_int(baseline)
    cand = _as_int(candidate)
    status = "passed" if cand <= base else "failed"
    return GateCheck(
        name=name,
        status=status,
        baseline=base,
        candidate=cand,
        message="candidate pressure must not increase",
    )


def _case_rank_checks(baseline_pressure: dict[str, Any], candidate_pressure: dict[str, Any]) -> list[GateCheck]:
    baseline_items = _pressure_items_by_case(baseline_pressure)
    candidate_items = _pressure_items_by_case(candidate_pressure)
    checks: list[GateCheck] = []
    for case_id in sorted(set(baseline_items).intersection(candidate_items)):
        base_rank = _as_int(baseline_items[case_id].get("first_matched_rank"))
        cand_rank = _as_int(candidate_items[case_id].get("first_matched_rank"))
        checks.append(
            GateCheck(
                name=f"case_first_matched_rank:{case_id}",
                status="passed" if cand_rank <= base_rank else "failed",
                baseline=base_rank,
                candidate=cand_rank,
                message="tracked pressure case must not move later",
            )
        )
    return checks


def _new_pressure_case_checks(baseline_pressure: dict[str, Any], candidate_pressure: dict[str, Any]) -> list[GateCheck]:
    baseline_items = _pressure_items_by_case(baseline_pressure)
    candidate_items = _pressure_items_by_case(candidate_pressure)
    checks: list[GateCheck] = []
    for case_id in sorted(set(candidate_items) - set(baseline_items)):
        cand_rank = _as_int(candidate_items[case_id].get("first_matched_rank"))
        checks.append(
            GateCheck(
                name=f"new_pressure_case:{case_id}",
                status="failed",
                baseline="absent",
                candidate=cand_rank,
                message="candidate must not introduce new ranking-pressure cases",
            )
        )
    return checks


def _pressure_items_by_case(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = report.get("items")
    if not isinstance(items, list):
        return {}
    return {
        str(item.get("case_id") or ""): item
        for item in items
        if isinstance(item, dict) and str(item.get("case_id") or "")
    }


def _bounded_summary(readiness: dict[str, Any], pressure: dict[str, Any]) -> dict[str, Any]:
    general = _stage_detail(readiness, "general_web_retrieval")
    pressure_summary = _summary(pressure)
    return {
        "release_readiness_status": str(readiness.get("status") or ""),
        "general_web_retrieval": {
            "hit_at_k": round(_as_float(general.get("hit_at_k")), 6),
            "recall_at_k": round(_as_float(general.get("recall_at_k")), 6),
            "mrr": round(_as_float(general.get("mrr")), 6),
        },
        "ranking_pressure": {
            "ranking_pressure_count": _as_int(pressure_summary.get("ranking_pressure_count")),
            "highest_pressure_rank_count": _as_int(pressure_summary.get("highest_pressure_rank_count")),
        },
    }


def _next_steps(checks: list[GateCheck]) -> list[str]:
    failed = [check.name for check in checks if check.status == "failed"]
    if not failed:
        return ["Candidate satisfies the bounded reranking evaluation gate."]
    return [
        "Do not ship the candidate ranking change until failed gate checks are addressed: " + ", ".join(failed) + ".",
        "Regenerate candidate reports after the fix and rerun this gate.",
    ]


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _render_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _safe_reason(reason: str) -> str:
    value = " ".join(str(reason or "").split())
    return value[:160] or "reranking_eval_gate_failed"
