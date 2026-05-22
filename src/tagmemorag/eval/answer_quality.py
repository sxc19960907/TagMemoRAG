from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from .dataset import EvalSuiteError


ANSWER_QUALITY_SCHEMA_VERSION = "answer_quality.v1"
MAX_REASON_LENGTH = 160


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class AnswerQualityContext:
    citation_id: str
    text: str = ""
    source: str = ""


@dataclass(frozen=True)
class AnswerQualityExpected:
    grounded: bool
    relevant: bool = True
    citation_supported: bool = True
    refusal_expected: bool = False


@dataclass(frozen=True)
class AnswerQualityCase:
    id: str
    question: str
    answer: str
    contexts: tuple[AnswerQualityContext, ...]
    expected: AnswerQualityExpected
    notes: str = ""


@dataclass(frozen=True)
class AnswerQualityCaseResult:
    id: str
    passed: bool
    scores: dict[str, float]
    expected: dict[str, bool]
    observed: dict[str, bool]
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "passed": self.passed,
            "scores": self.scores,
            "expected": self.expected,
            "observed": self.observed,
            "failures": self.failures,
        }
        if self.warnings:
            data["warnings"] = self.warnings
        return data


@dataclass(frozen=True)
class AnswerQualitySummary:
    cases: int
    passed: bool
    dimensions: dict[str, dict[str, int]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases": self.cases,
            "passed": self.passed,
            "dimensions": self.dimensions,
        }


@dataclass(frozen=True)
class AnswerQualityReport:
    suite: str
    summary: AnswerQualitySummary
    cases: list[AnswerQualityCaseResult]
    generated_at: str = field(default_factory=_utc_now)
    schema_version: str = ANSWER_QUALITY_SCHEMA_VERSION
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "suite": self.suite,
            "summary": self.summary.to_dict(),
            "cases": [case.to_dict() for case in self.cases],
        }
        if self.warnings:
            data["warnings"] = self.warnings
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def write_json(self, path: str | Path) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.to_json() + "\n", encoding="utf-8")


def load_answer_quality_suite(path: str | Path) -> list[AnswerQualityCase]:
    suite_path = Path(path)
    cases: list[AnswerQualityCase] = []
    seen_ids: set[str] = set()
    try:
        lines = suite_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EvalSuiteError(f"Could not read answer-quality suite {suite_path}: {exc}") from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvalSuiteError(f"{suite_path}:{line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(raw, dict):
            raise EvalSuiteError(f"{suite_path}:{line_number}: each JSONL row must be an object")
        case = _parse_case(raw, suite_path, line_number)
        if case.id in seen_ids:
            raise EvalSuiteError(f"{suite_path}:{line_number}: duplicate case id: {case.id}")
        seen_ids.add(case.id)
        cases.append(case)
    if not cases:
        raise EvalSuiteError(f"{suite_path}: answer-quality suite is empty")
    return cases


def run_answer_quality_diagnostics(suite_path: str | Path) -> AnswerQualityReport:
    cases = load_answer_quality_suite(suite_path)
    case_results = [evaluate_answer_quality_case(case) for case in cases]
    summary = _summarize(case_results)
    return AnswerQualityReport(suite=str(suite_path), summary=summary, cases=case_results)


def evaluate_answer_quality_case(case: AnswerQualityCase) -> AnswerQualityCaseResult:
    citation_ids = {context.citation_id for context in case.contexts if context.citation_id}
    cited_ids = set(_extract_citation_ids(case.answer))
    observed = {
        "grounded": _has_all_support_markers(case.answer, case.contexts),
        "relevant": _overlaps_question(case.question, case.answer),
        "citation_supported": bool(cited_ids) and cited_ids.issubset(citation_ids),
        "refusal": _looks_like_refusal(case.answer),
    }
    expected = {
        "grounded": case.expected.grounded,
        "relevant": case.expected.relevant,
        "citation_supported": case.expected.citation_supported,
        "refusal": case.expected.refusal_expected,
    }
    scores = {dimension: 1.0 if value else 0.0 for dimension, value in observed.items()}
    failures = [
        _bounded_reason(f"{dimension} expected {expected_value} observed {observed[dimension]}")
        for dimension, expected_value in expected.items()
        if observed[dimension] != expected_value
    ]
    warnings: list[str] = []
    unknown_citations = sorted(cited_ids - citation_ids)
    if unknown_citations:
        warnings.append(_bounded_reason("unknown citations: " + ", ".join(unknown_citations)))
    return AnswerQualityCaseResult(
        id=case.id,
        passed=not failures,
        scores=scores,
        expected=expected,
        observed=observed,
        failures=failures,
        warnings=warnings,
    )


def _parse_case(raw: dict[str, Any], suite_path: Path, line_number: int) -> AnswerQualityCase:
    case_id = _required_string(raw, "id", suite_path, line_number)
    contexts_raw = raw.get("contexts")
    if not isinstance(contexts_raw, list):
        raise EvalSuiteError(f"{suite_path}:{line_number}: case {case_id} contexts must be a list")
    contexts = tuple(_parse_context(item, case_id, suite_path, line_number) for item in contexts_raw)
    return AnswerQualityCase(
        id=case_id,
        question=_required_string(raw, "question", suite_path, line_number),
        answer=_required_string(raw, "answer", suite_path, line_number),
        contexts=contexts,
        expected=_parse_expected(raw.get("expected"), case_id, suite_path, line_number),
        notes=str(raw.get("notes") or ""),
    )


def _parse_context(raw: Any, case_id: str, suite_path: Path, line_number: int) -> AnswerQualityContext:
    if not isinstance(raw, dict):
        raise EvalSuiteError(f"{suite_path}:{line_number}: case {case_id} context entries must be objects")
    citation_id = _required_string(raw, "citation_id", suite_path, line_number)
    return AnswerQualityContext(
        citation_id=citation_id,
        text=str(raw.get("text") or ""),
        source=str(raw.get("source") or ""),
    )


def _parse_expected(raw: Any, case_id: str, suite_path: Path, line_number: int) -> AnswerQualityExpected:
    if not isinstance(raw, dict):
        raise EvalSuiteError(f"{suite_path}:{line_number}: case {case_id} expected must be an object")
    return AnswerQualityExpected(
        grounded=_required_bool(raw, "grounded", case_id, suite_path, line_number),
        relevant=_optional_bool(raw, "relevant", True, case_id, suite_path, line_number),
        citation_supported=_optional_bool(raw, "citation_supported", True, case_id, suite_path, line_number),
        refusal_expected=_optional_bool(raw, "refusal_expected", False, case_id, suite_path, line_number),
    )


def _required_string(raw: dict[str, Any], key: str, suite_path: Path, line_number: int) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvalSuiteError(f"{suite_path}:{line_number}: missing or empty required field: {key}")
    return value.strip()


def _required_bool(raw: dict[str, Any], key: str, case_id: str, suite_path: Path, line_number: int) -> bool:
    if key not in raw or not isinstance(raw[key], bool):
        raise EvalSuiteError(f"{suite_path}:{line_number}: case {case_id} {key} must be boolean")
    return bool(raw[key])


def _optional_bool(raw: dict[str, Any], key: str, default: bool, case_id: str, suite_path: Path, line_number: int) -> bool:
    if key not in raw:
        return default
    if not isinstance(raw[key], bool):
        raise EvalSuiteError(f"{suite_path}:{line_number}: case {case_id} {key} must be boolean")
    return bool(raw[key])


def _extract_citation_ids(answer: str) -> list[str]:
    return re.findall(r"\[([A-Za-z0-9_.:-]+)\]", answer)


def _has_all_support_markers(answer: str, contexts: tuple[AnswerQualityContext, ...]) -> bool:
    markers = re.findall(r"\{\{support:([^}]+)\}\}", answer)
    if markers:
        haystack = "\n".join(context.text.casefold() for context in contexts)
        return all(marker.strip().casefold() in haystack for marker in markers if marker.strip())
    cited_ids = set(_extract_citation_ids(answer))
    if not cited_ids:
        return False
    contexts_by_citation = {context.citation_id: context.text.casefold() for context in contexts}
    answer_terms = _content_terms(answer)
    if not answer_terms:
        return False
    cited_text = " ".join(contexts_by_citation.get(citation_id, "") for citation_id in cited_ids)
    return bool(answer_terms & _content_terms(cited_text))


def _overlaps_question(question: str, answer: str) -> bool:
    question_terms = _content_terms(question)
    if not question_terms:
        return True
    return bool(question_terms & _content_terms(answer))


def _content_terms(text: str) -> set[str]:
    cleaned = re.sub(r"\[[^\]]+\]|\{\{support:[^}]+\}\}", " ", text.casefold())
    return {term for term in re.findall(r"[a-z0-9\u4e00-\u9fff]{2,}", cleaned) if term not in {"the", "and", "with", "from"}}


def _looks_like_refusal(answer: str) -> bool:
    lowered = answer.casefold()
    refusal_markers = (
        "insufficient",
        "not enough evidence",
        "available evidence is insufficient",
        "cannot determine",
        "无法判断",
        "证据不足",
        "没有足够",
    )
    return any(marker in lowered for marker in refusal_markers)


def _summarize(case_results: list[AnswerQualityCaseResult]) -> AnswerQualitySummary:
    dimensions: dict[str, dict[str, int]] = {}
    for result in case_results:
        for dimension, expected in result.expected.items():
            bucket = dimensions.setdefault(dimension, {"passed": 0, "failed": 0})
            if result.observed[dimension] == expected:
                bucket["passed"] += 1
            else:
                bucket["failed"] += 1
    return AnswerQualitySummary(
        cases=len(case_results),
        passed=all(result.passed for result in case_results),
        dimensions=dimensions,
    )


def _bounded_reason(text: str) -> str:
    return text if len(text) <= MAX_REASON_LENGTH else text[: MAX_REASON_LENGTH - 3] + "..."
