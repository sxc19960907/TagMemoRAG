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


SCHEMA_VERSION = "same_page_ordering_diagnostic.v1"
NEAR_TIE_SCORE_DELTA = 0.05


@dataclass(frozen=True)
class SamePageOrderingResult:
    rank: int
    score: float
    score_gap_from_top: float
    matched: bool
    matched_expected_indexes: list[int]
    source_file: str
    header: str
    query_term_coverage: float
    usefulness_score: float
    definition_cues: int
    action_cues: int
    chrome_cues: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "score": self.score,
            "score_gap_from_top": self.score_gap_from_top,
            "matched": self.matched,
            "matched_expected_indexes": list(self.matched_expected_indexes),
            "source_file": self.source_file,
            "header": self.header,
            "query_term_coverage": self.query_term_coverage,
            "usefulness_score": self.usefulness_score,
            "definition_cues": self.definition_cues,
            "action_cues": self.action_cues,
            "chrome_cues": self.chrome_cues,
        }


@dataclass(frozen=True)
class SamePageOrderingCase:
    case_id: str
    kb_name: str
    metrics: dict[str, float]
    first_matched_rank: int
    pressure_rank_count: int
    repeated_source_file_count: int
    repeated_header_count: int
    dominant_source_file: str
    dominant_header: str
    top_to_first_match_score_gap: float
    near_tie_before_match_count: int
    average_matched_usefulness: float
    average_pre_match_usefulness: float
    best_pre_match_usefulness: float
    matched_beats_pre_match: bool
    diagnosis: str
    results: list[SamePageOrderingResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "kb_name": self.kb_name,
            "metrics": dict(self.metrics),
            "first_matched_rank": self.first_matched_rank,
            "pressure_rank_count": self.pressure_rank_count,
            "repeated_source_file_count": self.repeated_source_file_count,
            "repeated_header_count": self.repeated_header_count,
            "dominant_source_file": self.dominant_source_file,
            "dominant_header": self.dominant_header,
            "top_to_first_match_score_gap": self.top_to_first_match_score_gap,
            "near_tie_before_match_count": self.near_tie_before_match_count,
            "average_matched_usefulness": self.average_matched_usefulness,
            "average_pre_match_usefulness": self.average_pre_match_usefulness,
            "best_pre_match_usefulness": self.best_pre_match_usefulness,
            "matched_beats_pre_match": self.matched_beats_pre_match,
            "diagnosis": self.diagnosis,
            "results": [result.to_dict() for result in self.results],
        }


@dataclass(frozen=True)
class SamePageOrderingReport:
    report_path: str
    suite: str
    summary: dict[str, Any]
    cases: list[SamePageOrderingCase] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "report_path": self.report_path,
            "suite": self.suite,
            "summary": _report_summary(self.summary, self.cases),
            "cases": [case.to_dict() for case in self.cases],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        summary = _report_summary(self.summary, self.cases)
        lines = [
            "# Same-Page Ordering Diagnostic",
            "",
            f"- Report: `{self.report_path}`",
            f"- Suite: `{self.suite}`",
            f"- Pressure cases: `{summary['same_page_pressure_count']}`",
            f"- Highest pressure rank count: `{summary['highest_pressure_rank_count']}`",
            "",
            "| Case | First Match | Pressure | Source Repeat | Header Repeat | Score Gap | Near Ties | Diagnosis |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
        for case in self.cases:
            lines.append(
                "| "
                f"`{case.case_id}` | "
                f"{case.first_matched_rank} | "
                f"{case.pressure_rank_count} | "
                f"{case.repeated_source_file_count} | "
                f"{case.repeated_header_count} | "
                f"{case.top_to_first_match_score_gap:.6f} | "
                f"{case.near_tie_before_match_count} | "
                f"`{case.diagnosis}` |"
            )
        return "\n".join(lines) + "\n"


class SamePageOrderingInputError(ValueError):
    """Raised when an eval report cannot be summarized."""


def summarize_same_page_ordering(
    report_path: str | Path,
    *,
    max_results: int | None = None,
    near_tie_score_delta: float = NEAR_TIE_SCORE_DELTA,
) -> SamePageOrderingReport:
    try:
        usefulness = summarize_evidence_usefulness(report_path, max_results=max_results)
    except EvidenceUsefulnessInputError as exc:
        raise SamePageOrderingInputError(str(exc)) from exc
    payload = _load_report(Path(report_path))
    case_lookup = {str(case.get("id") or ""): case for case in payload.get("cases", []) if isinstance(case, dict)}
    cases = [
        item
        for case in usefulness.cases
        for item in [
            _case_to_same_page_ordering_case(
                case,
                raw_case=case_lookup.get(case.case_id, {}),
                near_tie_score_delta=near_tie_score_delta,
            )
        ]
        if item is not None
    ]
    cases.sort(key=lambda case: (-case.pressure_rank_count, case.case_id))
    return SamePageOrderingReport(
        report_path=usefulness.report_path,
        suite=usefulness.suite,
        summary=usefulness.summary,
        cases=cases,
    )


def render_report(report: SamePageOrderingReport, *, fmt: str) -> str:
    if fmt == "json":
        return report.to_json() + "\n"
    if fmt == "markdown":
        return report.to_markdown()
    raise SamePageOrderingInputError("format must be 'json' or 'markdown'")


def write_report(report: SamePageOrderingReport, output: str | Path, *, fmt: str) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(report, fmt=fmt), encoding="utf-8")


def _case_to_same_page_ordering_case(
    case: EvidenceUsefulnessCase,
    *,
    raw_case: dict[str, Any],
    near_tie_score_delta: float,
) -> SamePageOrderingCase | None:
    if case.first_matched_rank is None or case.first_matched_rank <= 1:
        return None
    raw_results = raw_case.get("actual_top_k")
    if not isinstance(raw_results, list):
        return None
    scored_results = _pair_scores(case.results, raw_results)
    if not scored_results:
        return None
    top_score = scored_results[0][1]
    first_match = next((pair for pair in scored_results if pair[0].rank == case.first_matched_rank), None)
    if first_match is None:
        return None
    sources = [result.source_file for result, _score in scored_results if result.source_file]
    headers = [result.header for result, _score in scored_results if result.header]
    dominant_source, source_count = _dominant_value(sources)
    dominant_header, header_count = _dominant_value(headers)
    if max(source_count, header_count) <= 1:
        return None
    first_match_score = first_match[1]
    pre_match_scores = [score for result, score in scored_results if result.rank < case.first_matched_rank]
    near_tie_count = sum(1 for score in pre_match_scores if abs(score - first_match_score) <= near_tie_score_delta)
    pressure_rank_count = case.first_matched_rank - 1
    return SamePageOrderingCase(
        case_id=case.case_id,
        kb_name=case.kb_name,
        metrics=dict(case.metrics),
        first_matched_rank=case.first_matched_rank,
        pressure_rank_count=pressure_rank_count,
        repeated_source_file_count=source_count,
        repeated_header_count=header_count,
        dominant_source_file=dominant_source,
        dominant_header=dominant_header,
        top_to_first_match_score_gap=round(top_score - first_match_score, 6),
        near_tie_before_match_count=near_tie_count,
        average_matched_usefulness=case.average_matched_usefulness,
        average_pre_match_usefulness=case.average_pre_match_usefulness,
        best_pre_match_usefulness=case.best_pre_match_usefulness,
        matched_beats_pre_match=case.matched_beats_pre_match,
        diagnosis=_diagnosis(
            source_count=source_count,
            header_count=header_count,
            pressure_rank_count=pressure_rank_count,
            matched_beats_pre_match=case.matched_beats_pre_match,
            near_tie_count=near_tie_count,
        ),
        results=[
            _to_ordering_result(result, score=score, top_score=top_score)
            for result, score in scored_results
        ],
    )


def _pair_scores(
    results: list[EvidenceUsefulnessResult],
    raw_results: list[Any],
) -> list[tuple[EvidenceUsefulnessResult, float]]:
    paired: list[tuple[EvidenceUsefulnessResult, float]] = []
    for index, result in enumerate(results):
        raw = raw_results[index] if index < len(raw_results) and isinstance(raw_results[index], dict) else {}
        paired.append((result, float(raw.get("score") or 0.0)))
    return paired


def _to_ordering_result(result: EvidenceUsefulnessResult, *, score: float, top_score: float) -> SamePageOrderingResult:
    return SamePageOrderingResult(
        rank=result.rank,
        score=round(score, 6),
        score_gap_from_top=round(top_score - score, 6),
        matched=result.matched,
        matched_expected_indexes=list(result.matched_expected_indexes),
        source_file=result.source_file,
        header=result.header,
        query_term_coverage=result.query_term_coverage,
        usefulness_score=result.usefulness_score,
        definition_cues=result.definition_cues,
        action_cues=result.action_cues,
        chrome_cues=result.chrome_cues,
    )


def _dominant_value(values: list[str]) -> tuple[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return "", 0
    return max(counts.items(), key=lambda item: (item[1], item[0]))


def _diagnosis(
    *,
    source_count: int,
    header_count: int,
    pressure_rank_count: int,
    matched_beats_pre_match: bool,
    near_tie_count: int,
) -> str:
    if matched_beats_pre_match and max(source_count, header_count) > pressure_rank_count:
        return "same_page_ordering_not_usefulness"
    if near_tie_count:
        return "same_page_near_tie"
    return "same_page_pressure"


def _report_summary(summary: dict[str, Any], cases: list[SamePageOrderingCase]) -> dict[str, Any]:
    return {
        **dict(summary),
        "same_page_pressure_count": len(cases),
        "highest_pressure_rank_count": max((case.pressure_rank_count for case in cases), default=0),
        "same_page_not_usefulness_count": sum(
            1 for case in cases if case.diagnosis == "same_page_ordering_not_usefulness"
        ),
        "near_tie_case_count": sum(1 for case in cases if case.near_tie_before_match_count > 0),
        "average_top_to_first_match_score_gap": round(
            _average(case.top_to_first_match_score_gap for case in cases),
            6,
        ),
    }


def _average(values: Any) -> float:
    numbers = [float(value) for value in values]
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def _load_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SamePageOrderingInputError(f"eval report not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SamePageOrderingInputError(f"eval report {path} is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise SamePageOrderingInputError(f"eval report {path} must contain a JSON object")
    if not isinstance(payload.get("cases"), list):
        raise SamePageOrderingInputError(f"eval report {path} is missing the 'cases' list")
    return payload
