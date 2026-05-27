from __future__ import annotations

import json
from typing import cast

from fastapi import UploadFile

from .api_models import SearchFilters, SearchRequest
from .auth.base import ApiKey
from .config import Settings
from .errors import ErrorCode, ServiceError
from .manual_bulk_import import BulkImportMode, BulkUploadedFile
from .manual_library import build_dirty_state_report, registry_inspect, verify_registry_blobs
from .metadata_narrowing import NarrowingDecision, infer_metadata_narrowing, merge_inferred_filters
from .rebuild_queue import RebuildQueue
from .state import AppState, start_library_rebuild
from .tag_governance import load_tag_policy, resolve_tags_for_search
from .types import GraphState


def parse_metadata_form(metadata: str) -> dict[str, object]:
    try:
        parsed = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise ServiceError(ErrorCode.INVALID_INPUT, "metadata must be valid JSON.", {"error": str(exc)}) from exc
    if not isinstance(parsed, dict):
        raise ServiceError(ErrorCode.INVALID_INPUT, "metadata must be a JSON object.")
    return parsed


def parse_rewrite_mode(value: str):
    mode = value.strip().lower()
    if mode not in {"merge", "rename"}:
        raise ServiceError(ErrorCode.INVALID_INPUT, "mode must be merge or rename.", {"mode": value})
    return mode


def parse_alias_mode(value: str | None):
    if value is None or not str(value).strip():
        return None
    mode = str(value).strip().lower()
    if mode not in {"synonym", "deprecated"}:
        raise ServiceError(
            ErrorCode.INVALID_INPUT,
            "policy_alias_mode must be synonym or deprecated.",
            {"policy_alias_mode": value},
        )
    return mode


def governed_filter_dict(kb_name: str, filters: SearchFilters | None, settings: Settings) -> dict[str, object]:
    filter_dict = filters.to_filter_dict() if filters else {}
    tags = filter_dict.get("tags")
    if isinstance(tags, list) and tags:
        policy = load_tag_policy(kb_name, settings)
        filter_dict["tags"] = resolve_tags_for_search([str(tag) for tag in tags], policy)
    return filter_dict


def resolved_filter_dict(
    request: SearchRequest,
    state: GraphState,
    settings: Settings,
) -> tuple[dict[str, object], NarrowingDecision]:
    explicit_filters = governed_filter_dict(request.kb_name, request.filters, settings)
    narrowing = infer_metadata_narrowing(
        query_text=request.question,
        graph=state.graph,
        explicit_filters=explicit_filters,
        enabled=settings.search.metadata_narrowing_enabled,
        category_policy=settings.search.metadata_narrowing_category_policy,
        brand_policy=settings.search.metadata_narrowing_brand_policy,
        min_candidates=settings.search.metadata_narrowing_min_candidates,
    )
    return merge_inferred_filters(explicit_filters, narrowing), narrowing


async def metadata_text_from_bulk_form(metadata: str, metadata_file: UploadFile | None) -> str:
    if metadata_file is not None:
        content = await metadata_file.read()
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ServiceError(ErrorCode.INVALID_INPUT, "metadata_file must be UTF-8 text.", {"error": str(exc)}) from exc
    if not metadata.strip():
        raise ServiceError(ErrorCode.INVALID_INPUT, "metadata or metadata_file is required.")
    return metadata


async def bulk_uploaded_files(files: list[UploadFile] | None) -> list[BulkUploadedFile]:
    uploaded: list[BulkUploadedFile] = []
    for file in files or []:
        if not file.filename:
            continue
        uploaded.append(BulkUploadedFile(filename=file.filename, content=await file.read()))
    return uploaded


def parse_selected_rows(selected_rows: str) -> set[int] | None:
    if not selected_rows.strip():
        return None
    try:
        parsed = json.loads(selected_rows)
    except json.JSONDecodeError as exc:
        raise ServiceError(
            ErrorCode.INVALID_INPUT,
            "selected_rows must be a JSON array of row numbers.",
            {"error": str(exc)},
        ) from exc
    if not isinstance(parsed, list):
        raise ServiceError(ErrorCode.INVALID_INPUT, "selected_rows must be a JSON array of row numbers.")
    rows: set[int] = set()
    for item in parsed:
        try:
            rows.add(int(item))
        except (TypeError, ValueError) as exc:
            raise ServiceError(
                ErrorCode.INVALID_INPUT,
                "selected_rows must contain only row numbers.",
                {"value": item},
            ) from exc
    return rows


def parse_bulk_mode(mode: str) -> BulkImportMode:
    if mode not in {"create_only", "upsert", "dry_run"}:
        raise ServiceError(ErrorCode.INVALID_INPUT, "mode must be create_only, upsert, or dry_run.", {"mode": mode})
    return cast(BulkImportMode, mode)


def request_library_rebuild(
    kb_name: str,
    *,
    mode: str,
    allow_fallback: bool,
    trigger: str,
    settings: Settings,
    app_state: AppState,
    embedder,
    get_rebuild_queue,
    top_level: bool = False,
) -> dict[str, object]:
    if settings.manual_library.rebuild_queue_enabled:
        queue = get_rebuild_queue()
        job, coalesced = queue.enqueue(kb_name, mode=mode, allow_fallback=allow_fallback, trigger=trigger)
        payload = job.to_dict(coalesced=coalesced)
        return payload if top_level else {"rebuild_task": None, "rebuild_job": payload}
    task = start_library_rebuild(
        app_state,
        kb_name,
        settings,
        embedder=embedder,
        mode=mode,
        allow_fallback=allow_fallback,
    )
    payload = task.to_dict()
    return payload if top_level else {"rebuild_task": payload}


def manual_library_diagnostics(
    kb_name: str,
    *,
    verify_blobs: bool,
    include_jobs: bool,
    job_status: str | None,
    api_key: ApiKey,
    settings: Settings,
    app_state: AppState,
    get_rebuild_queue,
) -> dict[str, object]:
    graph_state = app_state.kbs.get(kb_name)
    registry = registry_inspect(kb_name, settings)
    dirty_report = build_dirty_state_report(kb_name, settings, graph_state=graph_state)
    blob_health: dict[str, object] = {
        "checked": False,
        "checked_count": 0,
        "missing_count": 0,
        "missing": [],
        "blob_backend": settings.manual_library.blob_backend,
    }
    if registry.get("enabled") and verify_blobs:
        verified = verify_registry_blobs(kb_name, settings)
        blob_health.update(
            {
                "checked": True,
                "checked_count": int(verified.get("checked_count") or 0),
                "missing_count": int(verified.get("missing_count") or 0),
                "missing": verified.get("missing") or [],
            }
        )
    elif registry.get("enabled"):
        blob_health["status"] = "unchecked"
    else:
        blob_health["status"] = "registry_disabled"

    jobs: list[dict[str, object]] = []
    if settings.manual_library.rebuild_queue_enabled and include_jobs:
        queue = get_rebuild_queue()
        jobs = [
            job
            for job in queue.list_jobs(kb_name=kb_name, status=job_status)
            if api_key.allows_kb(str(job.get("kb_name") or ""))
        ]
    queue_payload = {"enabled": settings.manual_library.rebuild_queue_enabled, "jobs": jobs}
    operations = dirty_report.get("operations_summary") if isinstance(dirty_report.get("operations_summary"), dict) else {}
    pdf_quality = _safe_pdf_quality(graph_state)
    return {
        "kb_name": kb_name,
        "registry": registry,
        "blob_health": blob_health,
        "dirty": {
            "pending_changes": bool(dirty_report.get("pending_changes")),
            "dirty_manual_count": int(dirty_report.get("dirty_manual_count") or 0),
            "dirty_manuals": dirty_report.get("dirty_manuals") or [],
            "recovery_actions": dirty_report.get("recovery_actions") or [],
            "operations_summary": operations,
        },
        "rebuild_queue": queue_payload,
        "last_rebuild": {
            "current_build_id": dirty_report.get("current_build_id") or "",
            "last_successful_build_id": dirty_report.get("last_successful_build_id") or "",
            "last_impact_summary": dirty_report.get("last_impact_summary"),
            "qdrant_sync": dirty_report.get("last_qdrant_sync") or (operations or {}).get("qdrant_sync"),
            "pdf_quality": pdf_quality,
        },
        "recommendations": diagnostic_recommendations(registry, blob_health, dirty_report, jobs, pdf_quality=pdf_quality),
    }


def diagnostic_recommendations(
    registry: dict[str, object],
    blob_health: dict[str, object],
    dirty_report: dict[str, object],
    jobs: list[dict[str, object]],
    *,
    pdf_quality: dict[str, object] | None = None,
) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    if registry.get("enabled") and not blob_health.get("checked"):
        recommendations.append({"code": "verify_blobs", "label": "Verify registry blobs", "severity": "info"})
    if int(blob_health.get("missing_count") or 0) > 0:
        recommendations.append({"code": "restore_object_store", "label": "Restore missing blob objects before rebuild", "severity": "warning"})
    if dirty_report.get("pending_changes"):
        recommendations.append({"code": "inspect_dirty", "label": "Inspect dirty manuals", "severity": "warning"})
    if any(str(job.get("status")) == "failed" for job in jobs):
        recommendations.append({"code": "retry_rebuild", "label": "Retry failed queued rebuild", "severity": "warning"})
    if any(str(job.get("status")) in {"queued", "retrying"} for job in jobs):
        recommendations.append({"code": "inspect_queue", "label": "Inspect queued rebuild work", "severity": "info"})
    qdrant_sync = dirty_report.get("last_qdrant_sync")
    if isinstance(qdrant_sync, dict) and qdrant_sync.get("fallback_reason"):
        recommendations.append({"code": "force_full_rebuild", "label": "Force a full rebuild after Qdrant fallback", "severity": "warning"})
    pdf_quality = pdf_quality or {}
    warning_counts = pdf_quality.get("warning_counts") if isinstance(pdf_quality.get("warning_counts"), dict) else {}
    if int(pdf_quality.get("pages_missing_text") or 0) > 0 or bool(warning_counts):
        recommendations.append({"code": "review_pdf_quality", "label": "Review PDF parser quality summary", "severity": "warning"})
    if not registry.get("enabled"):
        recommendations.append({"code": "file_sidecar_mode", "label": "Registry disabled; using file sidecars", "severity": "info"})
    return recommendations


def _safe_pdf_quality(graph_state: object | None) -> dict[str, object]:
    meta = getattr(graph_state, "meta", None)
    if not isinstance(meta, dict):
        return {}
    quality = meta.get("pdf_quality")
    if not isinstance(quality, dict):
        return {}
    warning_counts = quality.get("warning_counts")
    if not isinstance(warning_counts, dict):
        warning_counts = {}
    return {
        "documents": _safe_non_negative_int(quality.get("documents")),
        "pages_total": _safe_non_negative_int(quality.get("pages_total")),
        "pages_with_text": _safe_non_negative_int(quality.get("pages_with_text")),
        "pages_missing_text": _safe_non_negative_int(quality.get("pages_missing_text")),
        "ocr_pages_created": _safe_non_negative_int(quality.get("ocr_pages_created")),
        "warning_counts": {
            str(key): _safe_non_negative_int(value)
            for key, value in sorted(warning_counts.items())
            if str(key).strip() and _safe_non_negative_int(value) > 0
        },
    }


def _safe_non_negative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def safe_audit_detail(detail: dict[str, object]) -> dict[str, object]:
    allowed = {"source_file", "status", "checksum", "blob_backend", "size_bytes", "content_type"}
    return {
        key: value
        for key, value in detail.items()
        if key in allowed and (isinstance(value, (str, int, float, bool)) or value is None)
    }


def require_rebuild_queue(settings: Settings, get_rebuild_queue) -> RebuildQueue:
    if not settings.manual_library.rebuild_queue_enabled:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Rebuild queue is not enabled.", {})
    return get_rebuild_queue()
