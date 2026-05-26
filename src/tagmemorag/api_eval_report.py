from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import ErrorCode, ServiceError

SCHEMA_VERSION = "eval_report_view.v1"
MAX_RESULTS_PER_CASE = 8


def load_eval_report_view(report_path: str | Path) -> dict[str, Any]:
    path_text = str(report_path).strip()
    if not path_text:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Eval report path is required.", {"field": "path"})
    path = Path(path_text).expanduser()
    if not path.exists():
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Eval report file was not found.", {"path": str(path)})
    if not path.is_file():
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Eval report path must be a file.", {"path": str(path)})
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ServiceError(
            ErrorCode.INVALID_REQUEST,
            "Eval report file is not valid JSON.",
            {"path": str(path), "line": exc.lineno, "column": exc.colno},
        ) from exc
    return summarize_eval_report_payload(payload, report_path=str(path))


def summarize_eval_report_payload(payload: Any, *, report_path: str = "") -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Eval report must be a JSON object.", {"path": report_path})
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Eval report is missing the cases list.", {"path": report_path})

    cases = [_case_summary(case) for case in raw_cases if isinstance(case, dict)]
    cases.sort(key=lambda item: (-int(item["severity"]), item["id"]))
    counts = _counts(cases)
    summary = _safe_dict(payload.get("summary"))
    return {
        "schema_version": SCHEMA_VERSION,
        "report_path": report_path,
        "suite": str(payload.get("suite") or ""),
        "docs": payload.get("docs") if payload.get("docs") is None else str(payload.get("docs")),
        "kb_names": _safe_str_list(payload.get("kb_names")),
        "top_k": _safe_int(payload.get("top_k")),
        "thresholds": _safe_dict(payload.get("thresholds")),
        "summary": summary,
        "counts": counts,
        "cases": cases,
        "config_snapshot": _safe_dict(payload.get("config_snapshot")),
    }


def _case_summary(case: dict[str, Any]) -> dict[str, Any]:
    metrics = _safe_metrics(case.get("metrics"))
    expected = _safe_list_of_dicts(case.get("expected"))
    actual = _safe_list_of_dicts(case.get("actual_top_k"))[:MAX_RESULTS_PER_CASE]
    failures = _safe_str_list(case.get("failures"))
    negative_hits = _safe_list_of_dicts(case.get("negative_hits"))
    matched = _matched_expected_indexes(actual)
    severity = _severity(case, metrics, failures, expected, matched, negative_hits)
    return {
        "id": str(case.get("id") or ""),
        "query": str(case.get("query") or ""),
        "kb_name": str(case.get("kb_name") or ""),
        "top_k": _safe_int(case.get("top_k")),
        "passed": bool(case.get("passed")),
        "status": "urgent" if severity >= 3 else "review" if severity > 0 else "ok",
        "severity": severity,
        "metrics": metrics,
        "thresholds": _safe_dict(case.get("thresholds")),
        "failures": failures,
        "expected": expected,
        "actual_top_k": actual,
        "matched_expected_indexes": matched,
        "search_strategy": str(case.get("search_strategy") or ""),
        "ann_candidate_count": _safe_int(case.get("ann_candidate_count")),
        "ann_fallback_reason": str(case.get("ann_fallback_reason") or ""),
        "negatives": _safe_list_of_dicts(case.get("negatives")),
        "negative_hits": negative_hits,
    }


def _severity(
    case: dict[str, Any],
    metrics: dict[str, float],
    failures: list[str],
    expected: list[dict[str, Any]],
    matched: list[int],
    negative_hits: list[dict[str, Any]],
) -> int:
    if failures or negative_hits:
        return 3
    if case.get("passed") is False:
        return 3
    if metrics.get("hit_at_k", 0.0) < 1.0 or metrics.get("recall_at_k", 0.0) <= 0.0:
        return 3
    if metrics.get("recall_at_k", 1.0) < 1.0 or metrics.get("mrr", 1.0) < 0.5:
        return 2
    if expected and not matched:
        return 1
    return 0


def _counts(cases: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"total": len(cases), "passed": 0, "failed": 0, "urgent": 0, "review": 0, "ok": 0}
    for case in cases:
        if case["passed"]:
            counts["passed"] += 1
        else:
            counts["failed"] += 1
        status = str(case["status"])
        if status in counts:
            counts[status] += 1
    return counts


def _matched_expected_indexes(results: list[dict[str, Any]]) -> list[int]:
    matched: set[int] = set()
    for result in results:
        for key in ("matched_expected_indexes", "matches", "matched"):
            value = result.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, int):
                        matched.add(item)
                    elif isinstance(item, str) and item.isdigit():
                        matched.add(int(item))
    return sorted(matched)


def _safe_metrics(value: Any) -> dict[str, float]:
    raw = _safe_dict(value)
    return {
        "precision_at_k": _safe_float(raw.get("precision_at_k")),
        "recall_at_k": _safe_float(raw.get("recall_at_k")),
        "mrr": _safe_float(raw.get("mrr")),
        "hit_at_k": _safe_float(raw.get("hit_at_k")),
    }


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _safe_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return 0.0
