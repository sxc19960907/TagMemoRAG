from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = "general_web_ranking_pressure.v1"

_WORD_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", re.IGNORECASE)

_DEFINITION_CUES = (
    " is ",
    " are ",
    " means ",
    " refers to ",
    " called ",
    " contains ",
    " include ",
    " includes ",
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
_ACTION_CUES = (
    "click",
    "select",
    "create",
    "add",
    "commit",
    "merge",
    "review",
    "request",
    "open",
    "type",
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
class RankingPressureResult:
    rank: int
    matched_expected_indexes: list[int]
    source_file: str
    header: str
    body_word_count: int
    definition_cues: int
    overview_cues: int
    action_cues: int
    chrome_cues: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "matched_expected_indexes": list(self.matched_expected_indexes),
            "source_file": self.source_file,
            "header": self.header,
            "body_word_count": self.body_word_count,
            "definition_cues": self.definition_cues,
            "overview_cues": self.overview_cues,
            "action_cues": self.action_cues,
            "chrome_cues": self.chrome_cues,
        }


@dataclass(frozen=True)
class RankingPressureItem:
    case_id: str
    kb_name: str
    metrics: dict[str, float]
    first_matched_rank: int
    expected_count: int
    matched_expected_indexes: list[int]
    pressure_rank_count: int
    top_results: list[RankingPressureResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "kb_name": self.kb_name,
            "metrics": dict(self.metrics),
            "first_matched_rank": self.first_matched_rank,
            "expected_count": self.expected_count,
            "matched_expected_indexes": list(self.matched_expected_indexes),
            "pressure_rank_count": self.pressure_rank_count,
            "top_results": [result.to_dict() for result in self.top_results],
        }


@dataclass(frozen=True)
class RankingPressureReport:
    report_path: str
    suite: str
    summary: dict[str, Any]
    items: list[RankingPressureItem] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "report_path": self.report_path,
            "suite": self.suite,
            "summary": {
                **dict(self.summary),
                "ranking_pressure_count": len(self.items),
                "highest_pressure_rank_count": max((item.pressure_rank_count for item in self.items), default=0),
            },
            "items": [item.to_dict() for item in self.items],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            "# General-Web Ranking Pressure",
            "",
            f"- Report: `{self.report_path}`",
            f"- Suite: `{self.suite}`",
            f"- Items: `{len(self.items)}`",
            "",
            "| Case | First Match | Recall | MRR | Pressure Ranks | Cue Summary |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
        for item in self.items:
            cue_summary = "; ".join(
                f"{result.rank}:def={result.definition_cues},overview={result.overview_cues},"
                f"action={result.action_cues},chrome={result.chrome_cues},matched={bool(result.matched_expected_indexes)}"
                for result in item.top_results
            )
            lines.append(
                "| "
                f"`{item.case_id}` | "
                f"{item.first_matched_rank} | "
                f"{_fmt_metric(item.metrics.get('recall_at_k'))} | "
                f"{_fmt_metric(item.metrics.get('mrr'))} | "
                f"{item.pressure_rank_count} | "
                f"{cue_summary} |"
            )
        return "\n".join(lines) + "\n"


class RankingPressureInputError(ValueError):
    """Raised when an eval report cannot be summarized."""


def summarize_ranking_pressure(
    report_path: str | Path,
    *,
    max_results_after_match: int = 0,
) -> RankingPressureReport:
    path = Path(report_path)
    payload = _load_report(path)
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise RankingPressureInputError(f"eval report {path} is missing the 'cases' list")
    items = [
        item
        for case in cases
        if isinstance(case, dict)
        for item in [_case_to_pressure_item(case, max_results_after_match=max_results_after_match)]
        if item is not None
    ]
    items.sort(key=lambda item: (-item.pressure_rank_count, item.case_id))
    return RankingPressureReport(
        report_path=str(path),
        suite=str(payload.get("suite") or ""),
        summary=_safe_summary(payload.get("summary")),
        items=items,
    )


def render_report(report: RankingPressureReport, *, fmt: str) -> str:
    if fmt == "json":
        return report.to_json() + "\n"
    if fmt == "markdown":
        return report.to_markdown()
    raise RankingPressureInputError("format must be 'json' or 'markdown'")


def write_report(report: RankingPressureReport, output: str | Path, *, fmt: str) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(report, fmt=fmt), encoding="utf-8")


def _case_to_pressure_item(case: dict[str, Any], *, max_results_after_match: int) -> RankingPressureItem | None:
    if str(case.get("id") or "") == "__suite__":
        return None
    metrics = _safe_metrics(case.get("metrics"))
    if metrics.get("hit_at_k", 0.0) <= 0.0 or metrics.get("recall_at_k", 0.0) <= 0.0:
        return None
    if metrics.get("mrr", 1.0) >= 1.0:
        return None
    top_k = case.get("actual_top_k")
    if not isinstance(top_k, list):
        return None
    first_rank = _first_matched_rank(top_k)
    if first_rank is None or first_rank <= 1:
        return None
    expected = case.get("expected") if isinstance(case.get("expected"), list) else []
    cutoff_rank = first_rank + max(0, max_results_after_match)
    top_results = [
        _result_to_pressure_result(index + 1, result)
        for index, result in enumerate(top_k[:cutoff_rank])
        if isinstance(result, dict)
    ]
    matched = sorted({index for result in top_results for index in result.matched_expected_indexes})
    return RankingPressureItem(
        case_id=str(case.get("id") or ""),
        kb_name=str(case.get("kb_name") or ""),
        metrics=metrics,
        first_matched_rank=first_rank,
        expected_count=len(expected),
        matched_expected_indexes=matched,
        pressure_rank_count=first_rank - 1,
        top_results=top_results,
    )


def _result_to_pressure_result(rank: int, result: dict[str, Any]) -> RankingPressureResult:
    text = str(result.get("text") or "")
    header = str(result.get("header") or "")
    combined = f"{header}\n{text}"
    return RankingPressureResult(
        rank=rank,
        matched_expected_indexes=[int(index) for index in result.get("matched_expected_indexes") or []],
        source_file=str(result.get("source_file") or ""),
        header=header,
        body_word_count=len(_WORD_RE.findall(text)),
        definition_cues=_cue_count(combined, _DEFINITION_CUES),
        overview_cues=_cue_count(combined, _OVERVIEW_CUES),
        action_cues=_cue_count(combined, _ACTION_CUES),
        chrome_cues=_cue_count(combined, _CHROME_CUES),
    )


def _first_matched_rank(results: list[Any]) -> int | None:
    for rank, result in enumerate(results, 1):
        if isinstance(result, dict) and result.get("matched_expected_indexes"):
            return rank
    return None


def _cue_count(text: str, cues: tuple[str, ...]) -> int:
    lowered = f" {text.lower()} "
    return sum(1 for cue in cues if cue in lowered)


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


def _load_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RankingPressureInputError(f"eval report not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RankingPressureInputError(f"eval report {path} is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise RankingPressureInputError(f"eval report {path} must contain a JSON object")
    return payload


def _fmt_metric(value: float | None) -> str:
    return f"{float(value or 0.0):.6f}"
