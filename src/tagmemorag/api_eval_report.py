from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import ErrorCode, ServiceError
from .release_readiness import DEFAULT_REPORT_PATHS

SCHEMA_VERSION = "eval_report_view.v1"
LIST_SCHEMA_VERSION = "eval_report_list.v1"
MAX_RESULTS_PER_CASE = 8
DEFAULT_REPORT_LIST_LIMIT = 20
MAX_REPORT_LIST_LIMIT = 50
MAX_DISCOVERY_FILES = 500
MAX_DISCOVERY_DEPTH = 5


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


def list_eval_report_candidates(*, project_root: str | Path | None = None, limit: int = DEFAULT_REPORT_LIST_LIMIT) -> dict[str, Any]:
    root = Path(project_root or Path.cwd()).resolve()
    bounded_limit = max(1, min(int(limit or DEFAULT_REPORT_LIST_LIMIT), MAX_REPORT_LIST_LIMIT))
    reports = discover_eval_report_candidates(project_root=root)
    return {
        "schema_version": LIST_SCHEMA_VERSION,
        "project_root": str(root),
        "count": min(len(reports), bounded_limit),
        "reports": reports[:bounded_limit],
    }


def discover_eval_report_candidates(*, project_root: str | Path | None = None) -> list[dict[str, Any]]:
    root = Path(project_root or Path.cwd()).resolve()
    candidates: dict[Path, dict[str, Any]] = {}
    for path in _discover_report_paths(root):
        candidate = _candidate_summary(path, root)
        if candidate is None:
            continue
        candidates[path] = candidate
    return sorted(candidates.values(), key=lambda item: (-float(item["modified_at"]), str(item["path"])))


def summarize_eval_report_payload(payload: Any, *, report_path: str = "") -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Eval report must be a JSON object.", {"path": report_path})
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Eval report is missing the cases list.", {"path": report_path})

    cases = [_case_summary(case) for case in raw_cases if isinstance(case, dict)]
    cases.sort(key=lambda item: (-int(item["severity"]), item["id"]))
    counts = _counts(cases)
    guidance_counts = _guidance_counts(cases)
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
        "guidance_counts": guidance_counts,
        "cases": cases,
        "config_snapshot": _safe_dict(payload.get("config_snapshot")),
    }


def _discover_report_paths(project_root: Path) -> list[Path]:
    roots = [project_root / ".tmp" / "eval" / "browser-runs", project_root / ".tmp"]
    for value in DEFAULT_REPORT_PATHS.values():
        path = (project_root / value).resolve()
        if _is_within(path, project_root):
            roots.append(path.parent)

    discovered: list[Path] = []
    seen_paths: set[Path] = set()
    seen_roots: set[Path] = set()
    for root in roots:
        resolved_root = root.resolve()
        if resolved_root in seen_roots or not _is_within(resolved_root, project_root) or not resolved_root.exists():
            continue
        seen_roots.add(resolved_root)
        if resolved_root.is_file():
            if _looks_like_report_path(resolved_root) and resolved_root not in seen_paths:
                seen_paths.add(resolved_root)
                discovered.append(resolved_root)
            continue
        if not resolved_root.is_dir():
            continue
        for path in resolved_root.rglob("*.json"):
            if len(discovered) >= MAX_DISCOVERY_FILES:
                return discovered
            if not _is_within(path.resolve(), resolved_root):
                continue
            if len(path.relative_to(resolved_root).parts) > MAX_DISCOVERY_DEPTH:
                continue
            if _looks_like_report_path(path):
                resolved_path = path.resolve()
                if resolved_path in seen_paths:
                    continue
                seen_paths.add(resolved_path)
                discovered.append(resolved_path)
    return discovered


def _looks_like_report_path(path: Path) -> bool:
    name = path.name.lower()
    parent = path.parent.name.lower()
    return path.suffix.lower() == ".json" and ("report" in name or "eval" in name or parent in {"eval", "browser-runs"})


def _candidate_summary(path: Path, project_root: Path) -> dict[str, Any] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    candidate: dict[str, Any] = {
        "path": str(path),
        "relative_path": _relative_path(path, project_root),
        "name": path.name,
        "modified_at": round(float(stat.st_mtime), 3),
        "size_bytes": int(stat.st_size),
        "valid": False,
        "suite": "",
        "kb_names": [],
        "passed": None,
        "cases": 0,
        "failed": 0,
        "error": "",
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        candidate["error"] = type(exc).__name__
        return candidate
    if not isinstance(payload, dict):
        candidate["error"] = "not_object"
        return candidate
    cases = payload.get("cases")
    summary = _safe_dict(payload.get("summary"))
    if not isinstance(cases, list):
        candidate["error"] = "missing_cases"
        return candidate
    case_summaries = [_case_summary(case) for case in cases if isinstance(case, dict)]
    counts = _counts(case_summaries)
    candidate.update(
        {
            "valid": True,
            "suite": str(payload.get("suite") or ""),
            "kb_names": _safe_str_list(payload.get("kb_names")),
            "passed": summary.get("passed") if isinstance(summary.get("passed"), bool) else None,
            "cases": counts["total"],
            "failed": counts["failed"],
            "error": "",
        }
    )
    return candidate


def _relative_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _case_summary(case: dict[str, Any]) -> dict[str, Any]:
    metrics = _safe_metrics(case.get("metrics"))
    expected = _safe_list_of_dicts(case.get("expected"))
    actual = _safe_list_of_dicts(case.get("actual_top_k"))[:MAX_RESULTS_PER_CASE]
    failures = _safe_str_list(case.get("failures"))
    negative_hits = _safe_list_of_dicts(case.get("negative_hits"))
    matched = _matched_expected_indexes(actual)
    guidance = _guidance(case, metrics, failures, expected, actual, matched, negative_hits)
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
        "primary_issue": guidance[0]["code"] if guidance else "",
        "guidance": guidance,
        "expected": expected,
        "actual_top_k": actual,
        "matched_expected_indexes": matched,
        "search_strategy": str(case.get("search_strategy") or ""),
        "ann_candidate_count": _safe_int(case.get("ann_candidate_count")),
        "ann_fallback_reason": str(case.get("ann_fallback_reason") or ""),
        "negatives": _safe_list_of_dicts(case.get("negatives")),
        "negative_hits": negative_hits,
    }


def _guidance(
    case: dict[str, Any],
    metrics: dict[str, float],
    failures: list[str],
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    matched: list[int],
    negative_hits: list[dict[str, Any]],
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    weak_matcher = _weak_matcher(expected)
    if negative_hits:
        items.append(_guidance_item(
            "negative_hit",
            "urgent",
            "Negative evidence retrieved",
            "A result marked as negative evidence appeared in the retrieved set.",
            "Inspect the negative hit and tighten metadata filters, tags, or eval negatives so unrelated evidence stops ranking.",
        ))
    if failures:
        items.append(_guidance_item(
            "threshold_failure",
            "urgent",
            "Threshold failure",
            "The eval runner reported one or more threshold failures for this case.",
            "Use the failed metric and case evidence below to decide whether to improve retrieval or adjust an unrealistic threshold.",
        ))
    if weak_matcher:
        items.append(_guidance_item(
            "weak_matcher",
            "review",
            "Expected matcher is weak",
            "This case has missing or underspecified expected evidence, so pass/fail signals may be hard to trust.",
            "Add a source file, section, text_contains phrase, anchor key, or metadata matcher before using this as a regression gate.",
        ))
    if expected and not matched and not weak_matcher:
        items.append(_guidance_item(
            "no_expected_match",
            "urgent",
            "No expected evidence matched",
            "None of the expected evidence matched the retrieved top results.",
            "Check whether the expected source is built into the KB, then review query wording, metadata narrowing, and matcher specificity.",
        ))
    elif expected and not weak_matcher and metrics.get("recall_at_k", 0.0) < 1.0:
        items.append(_guidance_item(
            "partial_recall",
            "review",
            "Only part of the expected evidence matched",
            "At least one expected evidence item matched, but recall is still below 1.0.",
            "Review the unmatched expected evidence and decide whether the eval case needs multiple passages or the retrieval depth should increase.",
        ))
    first_match_rank = _first_match_rank(actual)
    if not weak_matcher and (first_match_rank > 1 or (first_match_rank > 0 and metrics.get("mrr", 1.0) < 0.5)):
        items.append(_guidance_item(
            "low_rank",
            "review",
            "Expected evidence ranked too low",
            "The expected evidence was found, but not at the strongest rank.",
            "Compare the higher-ranked results with the expected passage and tune ranking, tags, or same-page ordering before changing the eval.",
        ))
    if not items and case.get("passed") is False:
        items.append(_guidance_item(
            "unclassified_failure",
            "review",
            "Review failed case",
            "The case failed without a more specific deterministic diagnosis.",
            "Inspect metrics, expected evidence, and actual results to decide whether the issue is corpus coverage, retrieval, or eval authoring.",
        ))
    return items


def _guidance_item(code: str, severity: str, title: str, explanation: str, next_action: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "explanation": explanation,
        "next_action": next_action,
    }


def _guidance_counts(cases: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        for item in case.get("guidance", []):
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "")
            if code:
                counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))


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


def _weak_matcher(expected: list[dict[str, Any]]) -> bool:
    if not expected:
        return True
    for item in expected:
        metadata = item.get("metadata")
        has_metadata = isinstance(metadata, dict) and bool(metadata)
        text_contains = item.get("text_contains")
        has_text = isinstance(text_contains, list) and any(str(value).strip() for value in text_contains)
        if item.get("source_file") or item.get("header") or item.get("anchor_key") or has_metadata or has_text:
            return False
    return True


def _first_match_rank(results: list[dict[str, Any]]) -> int:
    for index, result in enumerate(results, 1):
        matched = result.get("matched_expected_indexes")
        if isinstance(matched, list) and matched:
            return _safe_int(result.get("rank")) or index
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
