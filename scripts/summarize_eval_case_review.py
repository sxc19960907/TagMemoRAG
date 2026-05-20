"""Summarize a full eval JSON report into a bounded case-review queue.

This script does not run eval and does not edit fixtures. It reads an existing
`tagmemorag eval run --output` report and emits a privacy-bounded JSON or
Markdown summary for human fixture review.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from typing import Any

SCHEMA_VERSION = "eval_case_review.v1"


@dataclass(frozen=True)
class ReviewItem:
    case_id: str
    kb_name: str
    severity: int
    status: str
    reasons: list[str]
    metrics: dict[str, float]
    failures: list[str]
    expected_count: int
    matched_expected_indexes: list[int]
    top_results: list[dict[str, Any]]
    negative_hits: list[dict[str, Any]]
    query: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "case_id": self.case_id,
            "kb_name": self.kb_name,
            "severity": self.severity,
            "status": self.status,
            "reasons": list(self.reasons),
            "metrics": dict(self.metrics),
            "failures": list(self.failures),
            "expected_count": self.expected_count,
            "matched_expected_indexes": list(self.matched_expected_indexes),
            "top_results": [dict(item) for item in self.top_results],
            "negative_hits": [dict(item) for item in self.negative_hits],
        }
        if self.query is not None:
            data["query"] = self.query
        return data


@dataclass(frozen=True)
class CaseReviewReport:
    report_path: str
    suite: str
    summary: dict[str, Any]
    items: list[ReviewItem] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in self.items:
            counts[item.status] = counts.get(item.status, 0) + 1
        return {
            "schema_version": self.schema_version,
            "report_path": self.report_path,
            "suite": self.suite,
            "summary": {
                **dict(self.summary),
                "review_item_count": len(self.items),
                "status_counts": counts,
                "highest_severity": max((item.severity for item in self.items), default=0),
            },
            "items": [item.to_dict() for item in self.items],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            "# Eval Case Review",
            "",
            f"- Report: `{self.report_path}`",
            f"- Suite: `{self.suite}`",
            f"- Items: `{len(self.items)}`",
            "",
            "| Case | Status | Severity | Recall | MRR | Hit | Reasons | Top Results |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
        ]
        for item in self.items:
            top = "; ".join(f"{r['rank']}:{r.get('source_file', '')}#{r.get('header', '')}" for r in item.top_results[:3])
            reasons = ", ".join(item.reasons)
            lines.append(
                "| "
                f"`{item.case_id}` | "
                f"`{item.status}` | "
                f"{item.severity} | "
                f"{_fmt_metric(item.metrics.get('recall_at_k'))} | "
                f"{_fmt_metric(item.metrics.get('mrr'))} | "
                f"{_fmt_metric(item.metrics.get('hit_at_k'))} | "
                f"{reasons} | "
                f"{top} |"
            )
        return "\n".join(lines) + "\n"


class CaseReviewInputError(ValueError):
    """Raised when an eval report cannot be summarized."""


def summarize_eval_report(
    report_path: str | Path,
    *,
    include_query: bool = False,
    include_ok: bool = False,
    max_results: int = 5,
) -> CaseReviewReport:
    path = Path(report_path)
    payload = _load_report(path)
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise CaseReviewInputError(f"eval report {path} is missing the 'cases' list")
    items = [
        item
        for case in cases
        if isinstance(case, dict)
        for item in [_case_to_review_item(case, include_query=include_query, max_results=max_results)]
        if include_ok or item.severity > 0
    ]
    items.sort(key=lambda item: (-item.severity, item.case_id))
    return CaseReviewReport(
        report_path=str(path),
        suite=str(payload.get("suite") or ""),
        summary=_safe_summary(payload.get("summary")),
        items=items,
    )


def render_report(report: CaseReviewReport, *, fmt: str) -> str:
    if fmt == "json":
        return report.to_json() + "\n"
    if fmt == "markdown":
        return report.to_markdown()
    raise CaseReviewInputError("format must be 'json' or 'markdown'")


def write_report(report: CaseReviewReport, output: str | Path, *, fmt: str) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(report, fmt=fmt), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--include-query", action="store_true", default=False)
    parser.add_argument("--include-ok", action="store_true", default=False)
    parser.add_argument("--max-results", type=int, default=5)
    args = parser.parse_args(argv)

    try:
        report = summarize_eval_report(
            args.report,
            include_query=args.include_query,
            include_ok=args.include_ok,
            max_results=args.max_results,
        )
        if args.output is not None:
            write_report(report, args.output, fmt=args.format)
        else:
            print(render_report(report, fmt=args.format), end="")
        return 0
    except CaseReviewInputError as exc:
        print(f"eval case review error: {exc}", file=sys.stderr)
        return 2


def _case_to_review_item(case: dict[str, Any], *, include_query: bool, max_results: int) -> ReviewItem:
    metrics = _safe_metrics(case.get("metrics"))
    failures = [str(item) for item in case.get("failures") or []]
    expected = case.get("expected") if isinstance(case.get("expected"), list) else []
    negative_hits = _safe_negative_hits(case.get("negative_hits"))
    top_results = _safe_top_results(case.get("actual_top_k"), max_results=max_results)
    matched = _matched_expected_indexes(top_results)
    reasons = _reasons(metrics, failures, expected_count=len(expected), matched_count=len(matched), negative_hits=negative_hits)
    severity = _severity(reasons)
    status = "urgent" if severity >= 3 else "review" if severity > 0 else "ok"
    query = str(case.get("query") or "") if include_query else None
    return ReviewItem(
        case_id=str(case.get("id") or ""),
        kb_name=str(case.get("kb_name") or ""),
        severity=severity,
        status=status,
        reasons=reasons or ["no_review_signal"],
        metrics=metrics,
        failures=failures,
        expected_count=len(expected),
        matched_expected_indexes=matched,
        top_results=top_results,
        negative_hits=negative_hits,
        query=query,
    )


def _reasons(
    metrics: dict[str, float],
    failures: list[str],
    *,
    expected_count: int,
    matched_count: int,
    negative_hits: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if failures:
        reasons.append("has_failures")
    if negative_hits:
        reasons.append("has_negative_hits")
    if metrics.get("hit_at_k") == 0.0:
        reasons.append("hit_at_k_zero")
    if metrics.get("recall_at_k") == 0.0:
        reasons.append("recall_at_k_zero")
    if metrics.get("recall_at_k", 1.0) < 0.75:
        reasons.append("recall_at_k_below_0.75")
    if metrics.get("mrr", 1.0) < 0.5:
        reasons.append("mrr_below_0.5")
    if expected_count > 0 and matched_count < expected_count:
        reasons.append("matched_fewer_than_expected")
    if not reasons:
        if metrics.get("recall_at_k", 1.0) < 1.0:
            reasons.append("recall_at_k_below_1.0")
        if metrics.get("mrr", 1.0) < 1.0:
            reasons.append("mrr_below_1.0")
    return reasons


def _severity(reasons: list[str]) -> int:
    urgent = {"has_failures", "has_negative_hits", "hit_at_k_zero", "recall_at_k_zero"}
    if urgent & set(reasons):
        return 3
    review = {"recall_at_k_below_0.75", "mrr_below_0.5", "matched_fewer_than_expected"}
    if review & set(reasons):
        return 2
    if reasons:
        return 1
    return 0


def _safe_top_results(raw: Any, *, max_results: int) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or max_results <= 0:
        return []
    results: list[dict[str, Any]] = []
    for index, item in enumerate(raw[:max_results], start=1):
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "rank": index,
                "source_file": str(item.get("source_file") or ""),
                "header": str(item.get("header") or ""),
                "matched_expected_indexes": [int(v) for v in item.get("matched_expected_indexes") or []],
                "score": _round_float(item.get("score")),
            }
        )
    return results


def _matched_expected_indexes(top_results: list[dict[str, Any]]) -> list[int]:
    matched: set[int] = set()
    for result in top_results:
        matched.update(int(value) for value in result.get("matched_expected_indexes") or [])
    return sorted(matched)


def _safe_negative_hits(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    hits: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        hits.append(
            {
                "rank": int(item.get("rank") or 0),
                "negative_index": int(item.get("negative_index") or 0),
                "source_file": str(item.get("source_file") or ""),
            }
        )
    return hits


def _safe_metrics(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    return {str(key): _round_float(value) for key, value in raw.items() if isinstance(value, (int, float))}


def _safe_summary(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    allowed = {"cases", "passed", "precision_at_k", "recall_at_k", "mrr", "hit_at_k"}
    return {key: raw[key] for key in allowed if key in raw}


def _round_float(value: Any) -> float:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return 0.0


def _fmt_metric(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.6f}"


def _load_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise CaseReviewInputError(f"eval report not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CaseReviewInputError(f"eval report {path} is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise CaseReviewInputError(f"eval report {path} must contain a JSON object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
