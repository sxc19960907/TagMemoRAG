from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = "evidence_usefulness_diagnostic.v1"

_TERM_RE = re.compile(r"[a-z0-9\u3400-\u9fff]+", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", re.IGNORECASE)

_DEFINITION_PATTERNS = (
    r"\bis (?:a|an|the)\b",
    r"\bare (?:a|an|the|written|used|available)\b",
    r"\bmeans\b",
    r"\brefers to\b",
    r"\bas (?:a|an|the)\b",
    r"\bcontains?\b",
    r"\binclude?s?\b",
)
_ACTION_PATTERNS = (
    r"\bmust\b",
    r"\bshould\b",
    r"\bcan\b",
    r"\bif\b",
    r"\bwhen\b",
    r"\bchoose\b",
    r"\bselect\b",
    r"\buse\b",
    r"\bopen\b",
    r"\bclick\b",
    r"請",
    r"如果",
    r"使用",
    r"選擇",
)
_OVERVIEW_CUES = (
    "overview",
    "introduction",
    "in this article",
    "get started",
    "learn",
    "tutorial",
    "quickstart",
)
_CHROME_CUES = (
    "source:",
    "navigation",
    "copy as markdown",
    "article ",
    "next :",
    "previous",
    "table of contents",
)


@dataclass(frozen=True)
class EvidenceUsefulnessResult:
    rank: int
    matched: bool
    matched_expected_indexes: list[int]
    source_file: str
    header: str
    body_word_count: int
    query_term_coverage: float
    usefulness_score: float
    definition_cues: int
    overview_cues: int
    action_cues: int
    chrome_cues: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "matched": self.matched,
            "matched_expected_indexes": list(self.matched_expected_indexes),
            "source_file": self.source_file,
            "header": self.header,
            "body_word_count": self.body_word_count,
            "query_term_coverage": self.query_term_coverage,
            "usefulness_score": self.usefulness_score,
            "definition_cues": self.definition_cues,
            "overview_cues": self.overview_cues,
            "action_cues": self.action_cues,
            "chrome_cues": self.chrome_cues,
        }


@dataclass(frozen=True)
class EvidenceUsefulnessCase:
    case_id: str
    kb_name: str
    metrics: dict[str, float]
    first_matched_rank: int | None
    expected_count: int
    matched_expected_indexes: list[int]
    average_matched_usefulness: float
    average_pre_match_usefulness: float
    best_pre_match_usefulness: float
    matched_beats_pre_match: bool
    useful_evidence_under_ranked: bool
    results: list[EvidenceUsefulnessResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "kb_name": self.kb_name,
            "metrics": dict(self.metrics),
            "first_matched_rank": self.first_matched_rank,
            "expected_count": self.expected_count,
            "matched_expected_indexes": list(self.matched_expected_indexes),
            "average_matched_usefulness": self.average_matched_usefulness,
            "average_pre_match_usefulness": self.average_pre_match_usefulness,
            "best_pre_match_usefulness": self.best_pre_match_usefulness,
            "matched_beats_pre_match": self.matched_beats_pre_match,
            "useful_evidence_under_ranked": self.useful_evidence_under_ranked,
            "results": [result.to_dict() for result in self.results],
        }


@dataclass(frozen=True)
class EvidenceUsefulnessReport:
    report_path: str
    suite: str
    summary: dict[str, Any]
    cases: list[EvidenceUsefulnessCase] = field(default_factory=list)
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
            "# Evidence Usefulness Diagnostic",
            "",
            f"- Report: `{self.report_path}`",
            f"- Suite: `{self.suite}`",
            f"- Cases: `{summary['cases']}`",
            f"- Matched cases: `{summary['matched_cases']}`",
            f"- Useful evidence under-ranked: `{summary['useful_evidence_under_ranked_count']}`",
            "",
            "| Case | First Match | Matched Avg | Pre-Match Avg | Pre-Match Best | Under-Ranked | Cue Summary |",
            "| --- | ---: | ---: | ---: | ---: | --- | --- |",
        ]
        for case in self.cases:
            cue_summary = "; ".join(
                f"{result.rank}:score={result.usefulness_score:.6f},coverage={result.query_term_coverage:.6f},"
                f"matched={result.matched},def={result.definition_cues},action={result.action_cues},"
                f"chrome={result.chrome_cues}"
                for result in case.results
            )
            lines.append(
                "| "
                f"`{case.case_id}` | "
                f"{case.first_matched_rank or ''} | "
                f"{case.average_matched_usefulness:.6f} | "
                f"{case.average_pre_match_usefulness:.6f} | "
                f"{case.best_pre_match_usefulness:.6f} | "
                f"{case.useful_evidence_under_ranked} | "
                f"{cue_summary} |"
            )
        return "\n".join(lines) + "\n"


class EvidenceUsefulnessInputError(ValueError):
    """Raised when an eval report cannot be summarized."""


def summarize_evidence_usefulness(
    report_path: str | Path,
    *,
    max_results: int | None = None,
) -> EvidenceUsefulnessReport:
    path = Path(report_path)
    payload = _load_report(path)
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise EvidenceUsefulnessInputError(f"eval report {path} is missing the 'cases' list")
    summarized = [
        item
        for case in cases
        if isinstance(case, dict)
        for item in [_case_to_usefulness_case(case, max_results=max_results)]
        if item is not None
    ]
    return EvidenceUsefulnessReport(
        report_path=str(path),
        suite=str(payload.get("suite") or ""),
        summary=_safe_summary(payload.get("summary")),
        cases=summarized,
    )


def render_report(report: EvidenceUsefulnessReport, *, fmt: str) -> str:
    if fmt == "json":
        return report.to_json() + "\n"
    if fmt == "markdown":
        return report.to_markdown()
    raise EvidenceUsefulnessInputError("format must be 'json' or 'markdown'")


def write_report(report: EvidenceUsefulnessReport, output: str | Path, *, fmt: str) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(report, fmt=fmt), encoding="utf-8")


def _case_to_usefulness_case(case: dict[str, Any], *, max_results: int | None) -> EvidenceUsefulnessCase | None:
    if str(case.get("id") or "") == "__suite__":
        return None
    top_k = case.get("actual_top_k")
    if not isinstance(top_k, list):
        return None
    query_terms = _terms(str(case.get("query") or ""))
    limit = len(top_k) if max_results is None else max(0, max_results)
    results = [
        _result_to_usefulness_result(index + 1, result, query_terms=query_terms)
        for index, result in enumerate(top_k[:limit])
        if isinstance(result, dict)
    ]
    first_matched_rank = _first_matched_rank(results)
    matched_results = [result for result in results if result.matched]
    pre_match_results = [
        result
        for result in results
        if first_matched_rank is not None and result.rank < first_matched_rank and not result.matched
    ]
    average_matched = _average(result.usefulness_score for result in matched_results)
    average_pre_match = _average(result.usefulness_score for result in pre_match_results)
    best_pre_match = max((result.usefulness_score for result in pre_match_results), default=0.0)
    matched_beats_pre_match = bool(matched_results) and average_matched > best_pre_match
    useful_under_ranked = bool(
        matched_results
        and pre_match_results
        and first_matched_rank is not None
        and first_matched_rank > 1
        and average_matched <= best_pre_match
    )
    expected = case.get("expected") if isinstance(case.get("expected"), list) else []
    matched_indexes = sorted({index for result in results for index in result.matched_expected_indexes})
    return EvidenceUsefulnessCase(
        case_id=str(case.get("id") or ""),
        kb_name=str(case.get("kb_name") or ""),
        metrics=_safe_metrics(case.get("metrics")),
        first_matched_rank=first_matched_rank,
        expected_count=len(expected),
        matched_expected_indexes=matched_indexes,
        average_matched_usefulness=round(average_matched, 6),
        average_pre_match_usefulness=round(average_pre_match, 6),
        best_pre_match_usefulness=round(best_pre_match, 6),
        matched_beats_pre_match=matched_beats_pre_match,
        useful_evidence_under_ranked=useful_under_ranked,
        results=results,
    )


def _result_to_usefulness_result(
    rank: int,
    result: dict[str, Any],
    *,
    query_terms: set[str],
) -> EvidenceUsefulnessResult:
    text = str(result.get("text") or "")
    header = str(result.get("header") or "")
    combined = f"{header}\n{text}"
    matched = [int(index) for index in result.get("matched_expected_indexes") or []]
    coverage = _query_coverage(combined, query_terms)
    definition_cues = _regex_count(combined, _DEFINITION_PATTERNS)
    action_cues = _regex_count(combined, _ACTION_PATTERNS)
    overview_cues = _cue_count(combined, _OVERVIEW_CUES)
    chrome_cues = _cue_count(combined, _CHROME_CUES)
    return EvidenceUsefulnessResult(
        rank=rank,
        matched=bool(matched),
        matched_expected_indexes=matched,
        source_file=str(result.get("source_file") or ""),
        header=header,
        body_word_count=len(_WORD_RE.findall(text)),
        query_term_coverage=round(coverage, 6),
        usefulness_score=round(
            _usefulness_score(
                combined,
                query_terms,
                coverage=coverage,
                definition_cues=definition_cues,
                action_cues=action_cues,
                chrome_cues=chrome_cues,
            ),
            6,
        ),
        definition_cues=definition_cues,
        overview_cues=overview_cues,
        action_cues=action_cues,
        chrome_cues=chrome_cues,
    )


def _usefulness_score(
    text: str,
    query_terms: set[str],
    *,
    coverage: float,
    definition_cues: int,
    action_cues: int,
    chrome_cues: int,
) -> float:
    if not str(text).strip():
        return 0.0
    score = min(0.4, coverage)
    score += min(0.36, 0.12 * definition_cues)
    if coverage >= 0.35:
        score += min(0.12, 0.04 * action_cues)
    if _has_leading_chrome(text) or chrome_cues:
        score -= min(0.2, 0.08 * max(1, chrome_cues))
    return max(0.0, score)


def _terms(text: str) -> set[str]:
    return {token.lower() for token in _TERM_RE.findall(text) if len(token) >= 2}


def _query_coverage(text: str, query_terms: set[str]) -> float:
    if not query_terms:
        return 0.0
    terms = _terms(text)
    return len(terms.intersection(query_terms)) / max(1, len(query_terms))


def _first_matched_rank(results: list[EvidenceUsefulnessResult]) -> int | None:
    for result in results:
        if result.matched:
            return result.rank
    return None


def _average(values: Any) -> float:
    numbers = [float(value) for value in values]
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def _regex_count(text: str, patterns: tuple[str, ...]) -> int:
    normalized = f" {str(text).lower()} "
    return sum(1 for pattern in patterns if re.search(pattern, normalized))


def _cue_count(text: str, cues: tuple[str, ...]) -> int:
    lowered = f" {str(text).lower()} "
    return sum(1 for cue in cues if cue in lowered)


def _has_leading_chrome(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text).lower()).strip()
    return "source: http" in normalized[:180] or "navigation" in normalized[:180]


def _safe_metrics(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {"precision_at_k": 0.0, "recall_at_k": 0.0, "mrr": 0.0, "hit_at_k": 0.0}
    return {
        "precision_at_k": float(value.get("precision_at_k") or 0.0),
        "recall_at_k": float(value.get("recall_at_k") or 0.0),
        "mrr": float(value.get("mrr") or 0.0),
        "hit_at_k": float(value.get("hit_at_k") or 0.0),
    }


def _safe_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    summary: dict[str, Any] = {}
    for key in ("cases", "passed", "precision_at_k", "recall_at_k", "mrr", "hit_at_k"):
        if key in value:
            summary[key] = value[key]
    return summary


def _report_summary(summary: dict[str, Any], cases: list[EvidenceUsefulnessCase]) -> dict[str, Any]:
    matched_cases = [case for case in cases if case.first_matched_rank is not None]
    return {
        **dict(summary),
        "cases": len(cases),
        "matched_cases": len(matched_cases),
        "average_matched_usefulness": round(
            _average(case.average_matched_usefulness for case in matched_cases),
            6,
        ),
        "average_pre_match_usefulness": round(
            _average(case.average_pre_match_usefulness for case in matched_cases),
            6,
        ),
        "matched_beats_pre_match_count": sum(1 for case in matched_cases if case.matched_beats_pre_match),
        "useful_evidence_under_ranked_count": sum(1 for case in matched_cases if case.useful_evidence_under_ranked),
    }


def _load_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EvidenceUsefulnessInputError(f"eval report not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvidenceUsefulnessInputError(f"eval report {path} is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise EvidenceUsefulnessInputError(f"eval report {path} must contain a JSON object")
    return payload
