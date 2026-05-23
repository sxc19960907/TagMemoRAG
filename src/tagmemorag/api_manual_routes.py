from __future__ import annotations

from io import StringIO
import csv

import structlog
from fastapi.responses import Response

from .api_manual import (
    bulk_uploaded_files,
    manual_library_diagnostics,
    metadata_text_from_bulk_form,
    parse_alias_mode,
    parse_bulk_mode,
    parse_metadata_form,
    parse_rewrite_mode,
    parse_selected_rows,
    request_library_rebuild,
    require_rebuild_queue,
    safe_audit_detail,
)
from .api_models import (
    ManualLibraryRebuildRequest,
    ManualMetadataUpdateRequest,
    ManualMetadataValidationRequest,
    ManualTagSuggestRequest,
    TagPolicyUpdateRequest,
    TagRewriteRequest,
)
from .auth.base import ApiKey
from .auth.dependencies import ensure_kb_access
from .config import Settings
from .errors import ErrorCode, ServiceError
from .manual_bulk_import import commit_bulk_import, preview_bulk_import
from .manual_library import (
    build_dirty_state_report,
    delete_manual,
    disable_manual,
    library_root,
    list_records,
    load_manifest,
    registry_enabled,
    replace_manual_file,
    update_manual_metadata,
    upsert_manual,
    validate_metadata,
)
from .manual_registry import create_registry
from .manuals import metadata_from_node, public_tags_from_metadata
from .state import AppState
from .tag_governance import (
    commit_tag_rewrite,
    load_tag_policy,
    preview_tag_rewrite,
    save_tag_policy,
    tag_usage_report,
)
from .tag_suggestions import suggest_tags


def list_manuals(kb_name: str, api_key: ApiKey, settings: Settings, app_state: AppState) -> dict[str, object]:
    ensure_kb_access(api_key, kb_name)
    state = app_state.get_current(kb_name)
    manuals: dict[str, dict[str, object]] = {}
    facets: dict[str, set[str]] = {
        "brand": set(),
        "product_category": set(),
        "product_model": set(),
        "language": set(),
        "tags": set(),
    }
    for _, node in state.graph.nodes(data=True):
        metadata = metadata_from_node(node)
        manual_id = str(metadata.get("manual_id", "")).strip()
        if not manual_id:
            continue
        entry = manuals.setdefault(
            manual_id,
            {
                "manual_id": manual_id,
                "title": str(metadata.get("title", "")),
                "source_file": str(metadata.get("source_file", "")),
                "brand": str(metadata.get("brand", "")),
                "product_category": str(metadata.get("product_category", "")),
                "product_name": str(metadata.get("product_name", "")),
                "product_model": str(metadata.get("product_model", "")),
                "language": str(metadata.get("language", "")),
                "version": str(metadata.get("version", "")),
                "tags": public_tags_from_metadata(metadata),
                "chunk_count": 0,
            },
        )
        entry["chunk_count"] = int(entry["chunk_count"]) + 1
        for field in ("brand", "product_category", "product_model", "language"):
            value = str(metadata.get(field, "")).strip()
            if value:
                facets[field].add(value)
        facets["tags"].update(tag for tag in public_tags_from_metadata(metadata) if tag.strip())
    return {
        "kb_name": state.kb_name,
        "build_id": state.build_id,
        "manuals": sorted(manuals.values(), key=lambda item: str(item["manual_id"])),
        "facets": {key: sorted(values) for key, values in facets.items()},
    }


def validate_manual_metadata(request: ManualMetadataValidationRequest, api_key: ApiKey, settings: Settings) -> dict[str, object]:
    ensure_kb_access(api_key, request.kb_name)
    if request.mode not in {"create", "update", "upsert"}:
        raise ServiceError(ErrorCode.INVALID_INPUT, "mode must be create, update, or upsert.", {"mode": request.mode})
    result = validate_metadata(
        request.kb_name,
        dict(request.metadata),
        settings,
        mode=request.mode,  # type: ignore[arg-type]
        current_manual_id=request.current_manual_id,
        tag_policy=load_tag_policy(request.kb_name, settings),
    )
    return result.to_dict()


def suggest_manual_tags(
    request: ManualTagSuggestRequest,
    api_key: ApiKey,
    settings: Settings,
    app_state: AppState,
) -> dict[str, object]:
    ensure_kb_access(api_key, request.kb_name)
    graph_state = app_state.kbs.get(request.kb_name)
    records = list_records(request.kb_name, settings, graph_state=graph_state)
    policy = load_tag_policy(request.kb_name, settings)
    suggestions, existing_tags = suggest_tags(
        dict(request.metadata),
        records=records,
        graph_state=graph_state,
        text_sample=request.text_sample,
        limit=request.limit,
        tag_policy=policy,
    )
    return {
        "kb_name": request.kb_name,
        "suggestions": [suggestion.to_dict() for suggestion in suggestions],
        "existing_tags": existing_tags,
    }


async def upload_manual(
    *,
    kb_name: str,
    metadata: str,
    overwrite: bool,
    trigger_rebuild: bool,
    file,
    api_key: ApiKey,
    settings: Settings,
    app_state: AppState,
    embedder,
    get_rebuild_queue,
) -> dict[str, object]:
    ensure_kb_access(api_key, kb_name)
    metadata_obj = parse_metadata_form(metadata)
    content = await file.read()
    record = upsert_manual(kb_name, metadata_obj, content, settings, overwrite=overwrite or settings.manual_library.allow_overwrite)
    rebuild_payload = (
        request_library_rebuild(
            kb_name,
            mode="auto",
            allow_fallback=True,
            trigger="upload",
            settings=settings,
            app_state=app_state,
            embedder=embedder,
            get_rebuild_queue=get_rebuild_queue,
        )
        if trigger_rebuild
        else {}
    )
    structlog.get_logger().info("manual_library_mutation", kb_name=kb_name, manual_id=record.manual_id, action="upsert", status=record.status)
    return {"record": record.to_dict(), "rebuild_required": True, **rebuild_payload}


async def preview_manual_bulk_import(
    *,
    kb_name: str,
    metadata_format: str,
    metadata: str,
    mode: str,
    overwrite: bool,
    metadata_file,
    files,
    api_key: ApiKey,
    settings: Settings,
) -> dict[str, object]:
    ensure_kb_access(api_key, kb_name)
    metadata_text = await metadata_text_from_bulk_form(metadata, metadata_file)
    uploaded = await bulk_uploaded_files(files)
    preview = preview_bulk_import(
        kb_name,
        metadata_text,
        metadata_format,
        uploaded,
        settings,
        mode=parse_bulk_mode(mode),
        overwrite=overwrite,
    )
    structlog.get_logger().info(
        "manual_bulk_preview",
        kb_name=kb_name,
        row_count=len(preview.candidates),
        error_count=preview.error_count,
        warning_count=preview.warning_count,
        create_count=preview.create_count,
        update_count=preview.update_count,
    )
    return preview.to_dict()


async def import_manual_bulk(
    *,
    kb_name: str,
    metadata_format: str,
    metadata: str,
    mode: str,
    overwrite: bool,
    selected_rows: str,
    trigger_rebuild: bool,
    metadata_file,
    files,
    api_key: ApiKey,
    settings: Settings,
    app_state: AppState,
    embedder,
    get_rebuild_queue,
) -> dict[str, object]:
    ensure_kb_access(api_key, kb_name)
    metadata_text = await metadata_text_from_bulk_form(metadata, metadata_file)
    uploaded = await bulk_uploaded_files(files)
    result = commit_bulk_import(
        kb_name,
        metadata_text,
        metadata_format,
        uploaded,
        settings,
        mode=parse_bulk_mode(mode),
        overwrite=overwrite,
        selected_rows=parse_selected_rows(selected_rows),
    )
    rebuild_payload = (
        request_library_rebuild(
            kb_name,
            mode="auto",
            allow_fallback=True,
            trigger="bulk_import",
            settings=settings,
            app_state=app_state,
            embedder=embedder,
            get_rebuild_queue=get_rebuild_queue,
        )
        if trigger_rebuild and result.imported_count
        else {}
    )
    structlog.get_logger().info(
        "manual_bulk_import",
        kb_name=kb_name,
        row_count=len(result.preview.candidates) if result.preview else 0,
        imported_count=result.imported_count,
        failed_count=result.failed_count,
        skipped_count=result.skipped_count,
    )
    body = result.to_dict()
    body["rebuild_required"] = result.pending_rebuild
    body.update(rebuild_payload or {"rebuild_task": None})
    return body


def patch_manual_metadata(
    manual_id: str,
    request: ManualMetadataUpdateRequest,
    api_key: ApiKey,
    settings: Settings,
) -> dict[str, object]:
    ensure_kb_access(api_key, request.kb_name)
    record = update_manual_metadata(request.kb_name, manual_id, dict(request.metadata), settings)
    structlog.get_logger().info(
        "manual_library_mutation",
        kb_name=request.kb_name,
        manual_id=manual_id,
        action="metadata_update",
        status=record.status,
    )
    return {"record": record.to_dict(), "rebuild_required": True}


async def put_manual_file(manual_id: str, kb_name: str, file, api_key: ApiKey, settings: Settings) -> dict[str, object]:
    ensure_kb_access(api_key, kb_name)
    record = replace_manual_file(kb_name, manual_id, await file.read(), settings)
    structlog.get_logger().info("manual_library_mutation", kb_name=kb_name, manual_id=manual_id, action="file_replace", status=record.status)
    return {"record": record.to_dict(), "rebuild_required": True}


def remove_manual(manual_id: str, kb_name: str, hard: bool, api_key: ApiKey, settings: Settings) -> dict[str, object]:
    ensure_kb_access(api_key, kb_name)
    if hard and not api_key.has_scope("admin"):
        raise ServiceError(ErrorCode.FORBIDDEN, "Hard delete requires admin scope.", {"manual_id": manual_id})
    if hard:
        result = delete_manual(kb_name, manual_id, settings)
        structlog.get_logger().info("manual_library_mutation", kb_name=kb_name, manual_id=manual_id, action="hard_delete", status="deleted")
        return result
    record = disable_manual(kb_name, manual_id, settings)
    structlog.get_logger().info("manual_library_mutation", kb_name=kb_name, manual_id=manual_id, action="disable", status=record.status)
    return {"record": record.to_dict(), "rebuild_required": True}


def list_manual_library(
    kb_name: str,
    manual_id: str | None,
    api_key: ApiKey,
    settings: Settings,
    app_state: AppState,
) -> dict[str, object]:
    ensure_kb_access(api_key, kb_name)
    graph_state = app_state.kbs.get(kb_name)
    records = list_records(kb_name, settings, graph_state=graph_state)
    manifest = load_manifest(kb_name, settings)
    if manual_id is not None:
        records = [record for record in records if record.manual_id == manual_id]
        if not records:
            raise ServiceError(ErrorCode.INVALID_REQUEST, "Manual not found.", {"manual_id": manual_id, "kb_name": kb_name})
    return {
        "kb_name": kb_name,
        "library_root": str(library_root(kb_name, settings)),
        "pending_changes": manifest.pending_changes,
        "dirty_manual_count": len(manifest.dirty_manuals),
        "dirty_manuals": [dirty.to_dict() for dirty in manifest.dirty_manuals.values()],
        "manuals": [record.to_dict() for record in records],
    }


def manual_library_dirty(kb_name: str, format: str, api_key: ApiKey, settings: Settings, app_state: AppState):
    ensure_kb_access(api_key, kb_name)
    if format not in {"json", "csv"}:
        raise ServiceError(ErrorCode.INVALID_INPUT, "format must be json or csv.", {"format": format})
    report = build_dirty_state_report(kb_name, settings, graph_state=app_state.kbs.get(kb_name))
    rows = report["dirty_manuals"]
    if format == "csv":
        output = StringIO()
        fieldnames = ["manual_id", "source_file", "operation", "updated_at", "checksum", "status", "searchable", "exists"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return Response(output.getvalue(), media_type="text/csv")
    return report


def diagnostics(
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
    ensure_kb_access(api_key, kb_name)
    return manual_library_diagnostics(
        kb_name,
        verify_blobs=verify_blobs,
        include_jobs=include_jobs,
        job_status=job_status,
        api_key=api_key,
        settings=settings,
        app_state=app_state,
        get_rebuild_queue=get_rebuild_queue,
    )


def registry_audit(
    kb_name: str,
    manual_id: str | None,
    limit: int,
    api_key: ApiKey,
    settings: Settings,
) -> dict[str, object]:
    ensure_kb_access(api_key, kb_name)
    safe_limit = max(1, min(int(limit), 200))
    if not registry_enabled(settings):
        return {"kb_name": kb_name, "enabled": False, "events": [], "limit": safe_limit}
    events = create_registry(settings.manual_library.registry_path).audit_events(kb_name, manual_id=manual_id)
    newest_first = list(reversed(events))[:safe_limit]
    return {
        "kb_name": kb_name,
        "enabled": True,
        "manual_id": manual_id,
        "limit": safe_limit,
        "events": [
            {
                "event_id": event.event_id,
                "manual_id": event.manual_id,
                "operation": event.operation,
                "outcome": event.outcome,
                "version": event.version,
                "actor_id": event.actor_id,
                "created_at": event.created_at,
                "detail": safe_audit_detail(event.detail),
            }
            for event in newest_first
        ],
    }


def get_tags(kb_name: str, api_key: ApiKey, settings: Settings, app_state: AppState) -> dict[str, object]:
    ensure_kb_access(api_key, kb_name)
    graph_state = app_state.kbs.get(kb_name)
    return tag_usage_report(kb_name, settings, graph_state=graph_state)


def put_tag_policy(request: TagPolicyUpdateRequest, api_key: ApiKey, settings: Settings) -> dict[str, object]:
    ensure_kb_access(api_key, request.kb_name)
    policy = save_tag_policy(request.kb_name, settings, request.policy)
    structlog.get_logger().info(
        "tag_governance_policy_update",
        kb_name=request.kb_name,
        canonical_count=len(policy.canonical_tags),
        synonym_count=len(policy.synonyms),
        deprecated_count=len(policy.deprecated_tags),
    )
    return {"kb_name": request.kb_name, "policy": policy.to_dict()}


def preview_tag_rewrite(request: TagRewriteRequest, api_key: ApiKey, settings: Settings) -> dict[str, object]:
    ensure_kb_access(api_key, request.kb_name)
    mode = parse_rewrite_mode(request.mode)
    preview = preview_tag_rewrite_service(
        request.kb_name,
        settings,
        source_tags=request.source_tags,
        target_tag=request.target_tag,
        mode=mode,
    )
    return preview.to_dict()


def commit_tag_rewrite_route(request: TagRewriteRequest, api_key: ApiKey, settings: Settings) -> dict[str, object]:
    ensure_kb_access(api_key, request.kb_name)
    mode = parse_rewrite_mode(request.mode)
    alias_mode = parse_alias_mode(request.policy_alias_mode)
    result = commit_tag_rewrite(
        request.kb_name,
        settings,
        source_tags=request.source_tags,
        target_tag=request.target_tag,
        mode=mode,
        update_policy=request.update_policy,
        policy_alias_mode=alias_mode,
    )
    structlog.get_logger().info(
        "tag_governance_rewrite",
        kb_name=request.kb_name,
        operation=mode,
        updated_count=result.updated_count,
        failed_count=len(result.failures),
    )
    return result.to_dict()


def rebuild_library(
    request: ManualLibraryRebuildRequest,
    api_key: ApiKey,
    settings: Settings,
    app_state: AppState,
    embedder,
    get_rebuild_queue,
) -> dict[str, object]:
    ensure_kb_access(api_key, request.kb_name)
    if request.mode not in {"full", "incremental", "auto"}:
        raise ServiceError(ErrorCode.INVALID_INPUT, "rebuild mode must be full, incremental, or auto.", {"mode": request.mode})
    return request_library_rebuild(
        request.kb_name,
        mode=request.mode,
        allow_fallback=request.allow_fallback,
        trigger="api",
        settings=settings,
        app_state=app_state,
        embedder=embedder,
        get_rebuild_queue=get_rebuild_queue,
        top_level=True,
    )


def list_rebuild_jobs(kb_name: str | None, status: str | None, api_key: ApiKey, settings: Settings, get_rebuild_queue):
    if kb_name is not None:
        ensure_kb_access(api_key, kb_name)
    queue = require_rebuild_queue(settings, get_rebuild_queue)
    jobs = [
        job
        for job in queue.list_jobs(kb_name=kb_name, status=status)
        if api_key.allows_kb(str(job.get("kb_name") or ""))
    ]
    return {"jobs": jobs}


def inspect_rebuild_job(job_id: str, api_key: ApiKey, settings: Settings, get_rebuild_queue):
    queue = require_rebuild_queue(settings, get_rebuild_queue)
    job = queue.inspect(job_id)
    ensure_kb_access(api_key, str(job["kb_name"]))
    return job


def cancel_rebuild_job(job_id: str, api_key: ApiKey, settings: Settings, get_rebuild_queue) -> dict[str, object]:
    queue = require_rebuild_queue(settings, get_rebuild_queue)
    job = queue.get(job_id)
    ensure_kb_access(api_key, job.kb_name)
    cancelled = queue.cancel(job_id)
    return cancelled.to_dict()


def retry_rebuild_job(job_id: str, api_key: ApiKey, settings: Settings, get_rebuild_queue) -> dict[str, object]:
    queue = require_rebuild_queue(settings, get_rebuild_queue)
    job = queue.get(job_id)
    ensure_kb_access(api_key, job.kb_name)
    retried = queue.retry(job_id)
    return retried.to_dict()


# Avoid name clash with the route wrapper above.
from .tag_governance import preview_tag_rewrite as preview_tag_rewrite_service  # noqa: E402
