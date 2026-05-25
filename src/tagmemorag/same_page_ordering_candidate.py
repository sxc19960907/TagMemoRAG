from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .evidence_usefulness_diagnostic import (
    EvidenceUsefulnessCase,
    EvidenceUsefulnessInputError,
    EvidenceUsefulnessResult,
    summarize_evidence_usefulness,
)


SCHEMA_VERSION = "same_page_ordering_candidate.v1"


@dataclass(frozen=True)
class CandidateCaseResult:
    case_id: str
    kb_name: str
    baseline_metrics: dict[str, float]
    candidate_metrics: dict[str, float]
    baseline_first_matched_rank: int | None
    candidate_first_matched_rank: int | None
    baseline_pressure_rank_count: int
    candidate_pressure_rank_count: int
    matched_rank_delta: int
    same_page_dominant: bool
    changed: bool
    regressed: bool
    improved: bool
    candidate_order: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "kb_name": self.kb_name,
            "baseline_metrics": dict(self.baseline_metrics),
            "candidate_metrics": dict(self.candidate_metrics),
            "baseline_first_matched_rank": self.baseline_first_matched_rank,
            "candidate_first_matched_rank": self.candidate_first_matched_rank,
            "baseline_pressure_rank_count": self.baseline_pressure_rank_count,
            "candidate_pressure_rank_count": self.candidate_pressure_rank_count,
            "matched_rank_delta": self.matched_rank_delta,
            "same_page_dominant": self.same_page_dominant,
            "changed": self.changed,
            "regressed": self.regressed,
            "improved": self.improved,
            "candidate_order": [dict(item) for item in self.candidate_order],
        }


@dataclass(frozen=True)
class SamePageOrderingCandidateReport:
    report_path: str
    suite: str
    baseline_summary: dict[str, Any]
    candidate_summary: dict[str, Any]
    status: str
    cases: list[CandidateCaseResult] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "report_path": self.report_path,
            "suite": self.suite,
            "status": self.status,
            "baseline_summary": dict(self.baseline_summary),
            "candidate_summary": dict(self.candidate_summary),
            "cases": [case.to_dict() for case in self.cases],
            "next_steps": list(self.next_steps),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            "# Same-Page Ordering Candidate",
            "",
            f"- Status: `{self.status}`",
            f"- Report: `{self.report_path}`",
            f"- Suite: `{self.suite}`",
            f"- Improved cases: `{self.candidate_summary['improved_cases']}`",
            f"- Regressed cases: `{self.candidate_summary['regressed_cases']}`",
            f"- Baseline MRR: `{_fmt(self.baseline_summary.get('mrr'))}`",
            f"- Candidate MRR: `{_fmt(self.candidate_summary.get('mrr'))}`",
            "",
            "| Case | Dominant | Baseline Rank | Candidate Rank | Delta | Baseline MRR | Candidate MRR |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for case in self.cases:
            if not case.changed and not case.same_page_dominant:
                continue
            lines.append(
                "| "
                f"`{case.case_id}` | "
                f"{case.same_page_dominant} | "
                f"{case.baseline_first_matched_rank or ''} | "
                f"{case.candidate_first_matched_rank or ''} | "
                f"{case.matched_rank_delta} | "
                f"{_fmt(case.baseline_metrics.get('mrr'))} | "
                f"{_fmt(case.candidate_metrics.get('mrr'))} |"
            )
        if self.next_steps:
            lines.extend(["", "## Next Steps"])
            lines.extend(f"- {step}" for step in self.next_steps)
        return "\n".join(lines) + "\n"


class SamePageOrderingCandidateInputError(ValueError):
    """Raised when a candidate dry run cannot be summarized."""


def run_same_page_ordering_candidate(
    report_path: str | Path,
    *,
    max_results: int | None = None,
    dominance_threshold: int = 2,
) -> SamePageOrderingCandidateReport:
    try:
        usefulness = summarize_evidence_usefulness(report_path, max_results=max_results)
    except EvidenceUsefulnessInputError as exc:
        raise SamePageOrderingCandidateInputError(str(exc)) from exc
    cases = [
        _case_to_candidate_result(case, dominance_threshold=dominance_threshold)
        for case in usefulness.cases
    ]
    baseline_summary = _aggregate_summary(usefulness.summary, cases, baseline=True)
    candidate_summary = _aggregate_summary(usefulness.summary, cases, baseline=False)
    status = _candidate_status(cases)
    return SamePageOrderingCandidateReport(
        report_path=usefulness.report_path,
        suite=usefulness.suite,
        baseline_summary=baseline_summary,
        candidate_summary=candidate_summary,
        status=status,
        cases=cases,
        next_steps=_next_steps(status),
    )


def render_report(report: SamePageOrderingCandidateReport, *, fmt: str) -> str:
    if fmt == "json":
        return report.to_json() + "\n"
    if fmt == "markdown":
        return report.to_markdown()
    raise SamePageOrderingCandidateInputError("format must be 'json' or 'markdown'")


def write_report(report: SamePageOrderingCandidateReport, output: str | Path, *, fmt: str) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(report, fmt=fmt), encoding="utf-8")


def write_candidate_ranking_pressure(report: SamePageOrderingCandidateReport, output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_candidate_pressure_payload(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _case_to_candidate_result(case: EvidenceUsefulnessCase, *, dominance_threshold: int) -> CandidateCaseResult:
    same_page_dominant = _same_page_dominant(case.results, dominance_threshold=dominance_threshold)
    baseline_results = list(case.results)
    baseline_rank = _first_matched_rank(baseline_results)
    candidate_results = (
        _candidate_order(case.results)
        if same_page_dominant and baseline_rank is not None and baseline_rank > 1
        else baseline_results
    )
    baseline_metrics = _metrics_for_results(baseline_results, case.expected_count)
    candidate_metrics = _metrics_for_results(candidate_results, case.expected_count)
    candidate_rank = _first_matched_rank(candidate_results)
    baseline_pressure = _pressure_count(baseline_rank)
    candidate_pressure = _pressure_count(candidate_rank)
    delta = (baseline_rank or 0) - (candidate_rank or 0) if baseline_rank and candidate_rank else 0
    changed = [id(result) for result in baseline_results] != [id(result) for result in candidate_results]
    regressed = _regressed(baseline_rank, candidate_rank, baseline_metrics, candidate_metrics)
    improved = not regressed and (
        candidate_pressure < baseline_pressure or candidate_metrics["mrr"] > baseline_metrics["mrr"]
    )
    return CandidateCaseResult(
        case_id=case.case_id,
        kb_name=case.kb_name,
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
        baseline_first_matched_rank=baseline_rank,
        candidate_first_matched_rank=candidate_rank,
        baseline_pressure_rank_count=baseline_pressure,
        candidate_pressure_rank_count=candidate_pressure,
        matched_rank_delta=delta,
        same_page_dominant=same_page_dominant,
        changed=changed,
        regressed=regressed,
        improved=improved,
        candidate_order=[
            _candidate_order_item(index + 1, result)
            for index, result in enumerate(candidate_results)
        ],
    )


def _candidate_order(results: list[EvidenceUsefulnessResult]) -> list[EvidenceUsefulnessResult]:
    return sorted(
        results,
        key=lambda result: (
            -result.usefulness_score,
            -result.query_term_coverage,
            -int(result.matched),
            result.rank,
        ),
    )


def _candidate_order_item(candidate_rank: int, result: EvidenceUsefulnessResult) -> dict[str, Any]:
    return {
        "candidate_rank": candidate_rank,
        "baseline_rank": result.rank,
        "matched": result.matched,
        "matched_expected_indexes": list(result.matched_expected_indexes),
        "source_file": result.source_file,
        "header": result.header,
        "query_term_coverage": result.query_term_coverage,
        "usefulness_score": result.usefulness_score,
        "definition_cues": result.definition_cues,
        "action_cues": result.action_cues,
        "chrome_cues": result.chrome_cues,
    }


def _metrics_for_results(results: list[EvidenceUsefulnessResult], expected_count: int) -> dict[str, float]:
    matched_indexes = {index for result in results for index in result.matched_expected_indexes}
    retrieved = len(results)
    first_rank = _first_matched_rank(results)
    return {
        "precision_at_k": round(len([result for result in results if result.matched]) / max(1, retrieved), 6),
        "recall_at_k": round(len(matched_indexes) / max(1, expected_count), 6),
        "mrr": round(1.0 / first_rank if first_rank else 0.0, 6),
        "hit_at_k": 1.0 if first_rank else 0.0,
    }


def _first_matched_rank(results: list[EvidenceUsefulnessResult]) -> int | None:
    for rank, result in enumerate(results, 1):
        if result.matched:
            return rank
    return None


def _pressure_count(rank: int | None) -> int:
    return max(0, int(rank or 0) - 1) if rank else 0


def _same_page_dominant(results: list[EvidenceUsefulnessResult], *, dominance_threshold: int) -> bool:
    return max(_highest_count(result.source_file for result in results), _highest_count(result.header for result in results)) >= dominance_threshold


def _highest_count(values: Any) -> int:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        counts[str(value)] = counts.get(str(value), 0) + 1
    return max(counts.values(), default=0)


def _regressed(
    baseline_rank: int | None,
    candidate_rank: int | None,
    baseline_metrics: dict[str, float],
    candidate_metrics: dict[str, float],
) -> bool:
    if baseline_rank is not None and candidate_rank is None:
        return True
    if baseline_rank is not None and candidate_rank is not None and candidate_rank > baseline_rank:
        return True
    for metric in ("hit_at_k", "recall_at_k", "mrr"):
        if candidate_metrics[metric] + 1e-9 < baseline_metrics[metric]:
            return True
    return False


def _aggregate_summary(
    source_summary: dict[str, Any],
    cases: list[CandidateCaseResult],
    *,
    baseline: bool,
) -> dict[str, Any]:
    prefix = "baseline" if baseline else "candidate"
    metrics = [getattr(case, f"{prefix}_metrics") for case in cases]
    pressure_counts = [getattr(case, f"{prefix}_pressure_rank_count") for case in cases]
    return {
        "cases": len(cases),
        "passed": bool(source_summary.get("passed", True)),
        "precision_at_k": round(_average(metric["precision_at_k"] for metric in metrics), 6),
        "recall_at_k": round(_average(metric["recall_at_k"] for metric in metrics), 6),
        "mrr": round(_average(metric["mrr"] for metric in metrics), 6),
        "hit_at_k": round(_average(metric["hit_at_k"] for metric in metrics), 6),
        "ranking_pressure_count": sum(1 for count in pressure_counts if count > 0),
        "highest_pressure_rank_count": max(pressure_counts, default=0),
        "improved_cases": sum(1 for case in cases if case.improved),
        "unchanged_cases": sum(1 for case in cases if not case.improved and not case.regressed),
        "regressed_cases": sum(1 for case in cases if case.regressed),
        "changed_cases": sum(1 for case in cases if case.changed),
    }


def _candidate_status(cases: list[CandidateCaseResult]) -> str:
    if any(case.regressed for case in cases):
        return "failed"
    if any(case.improved for case in cases):
        return "passed"
    return "needs_review"


def _next_steps(status: str) -> list[str]:
    if status == "passed":
        return ["Candidate improved offline ranking pressure without observed regressions; design a guarded runtime experiment next."]
    if status == "needs_review":
        return ["Candidate produced no regressions but no clear improvements; inspect features before runtime work."]
    return ["Candidate regressed at least one case; do not proceed to runtime ranking work."]


def _candidate_pressure_payload(report: SamePageOrderingCandidateReport) -> dict[str, Any]:
    items = [
        {
            "case_id": case.case_id,
            "kb_name": case.kb_name,
            "metrics": dict(case.candidate_metrics),
            "first_matched_rank": case.candidate_first_matched_rank,
            "expected_count": 0,
            "matched_expected_indexes": [],
            "pressure_rank_count": case.candidate_pressure_rank_count,
            "top_results": [],
        }
        for case in report.cases
        if case.candidate_pressure_rank_count > 0 and case.candidate_first_matched_rank is not None
    ]
    return {
        "schema_version": "general_web_ranking_pressure.v1",
        "report_path": report.report_path,
        "suite": report.suite,
        "summary": {
            "cases": report.candidate_summary["cases"],
            "passed": report.candidate_summary["passed"],
            "precision_at_k": report.candidate_summary["precision_at_k"],
            "recall_at_k": report.candidate_summary["recall_at_k"],
            "mrr": report.candidate_summary["mrr"],
            "hit_at_k": report.candidate_summary["hit_at_k"],
            "ranking_pressure_count": report.candidate_summary["ranking_pressure_count"],
            "highest_pressure_rank_count": report.candidate_summary["highest_pressure_rank_count"],
        },
        "items": items,
    }


def _average(values: Any) -> float:
    numbers = [float(value) for value in values]
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def _fmt(value: Any) -> str:
    return f"{float(value or 0.0):.6f}"
