from __future__ import annotations

import structlog
from fastapi.responses import PlainTextResponse, Response

from .api_models import (
    CacheClearRequest,
    IndexGenBuildShadowRequest,
    IndexGenCancelShadowRequest,
    IndexGenRetireRequest,
    IndexGenSwapRequest,
)
from .config import Settings
from .errors import ErrorCode, ServiceError
from .observability.metrics import get_metrics, metrics_response_bytes
from .observability.tracing import start_span
from .state import AppState


def health_response() -> PlainTextResponse:
    return PlainTextResponse("ok", status_code=200)


def ready_response(app_state: AppState) -> PlainTextResponse:
    if app_state.is_shutting_down:
        return PlainTextResponse("shutting down", status_code=503)
    if not app_state.embedder_ready:
        return PlainTextResponse("embedder not ready", status_code=503)
    if app_state.current is None:
        return PlainTextResponse("kb not loaded", status_code=503)
    return PlainTextResponse("ok", status_code=200)


def metrics_endpoint_response(settings: Settings) -> Response:
    if not settings.observability.metrics.enabled:
        return PlainTextResponse("metrics disabled", status_code=404)
    if settings.observability.metrics.path != "/metrics":
        return PlainTextResponse("metrics not found", status_code=404)
    return metrics_response()


def metrics_response() -> Response:
    body, content_type = metrics_response_bytes()
    return Response(content=body, media_type=content_type)


def clear_cache(request: CacheClearRequest, settings: Settings, app_state: AppState) -> dict[str, object]:
    with start_span("tagmemorag.cache.clear", **{"tagmemorag.kb_name": request.kb_name or "all"}):
        if app_state.query_cache is None:
            get_metrics().record_cache_operation(operation="clear", outcome="disabled")
            return {"cleared_count": 0}
        cleared = app_state.query_cache.clear(request.kb_name)
        get_metrics().record_cache_operation(operation="clear", outcome="success")
        get_metrics().set_cache_entries(len(app_state.query_cache))
        structlog.get_logger().info("cache_cleared", kb_name=request.kb_name, cleared_count=cleared)
        return {"cleared_count": cleared}


def resolve_indexgen_target_versions(req: IndexGenBuildShadowRequest) -> dict[str, object]:
    diff: dict[str, object] = {}
    if req.embedding_model_id is not None:
        diff["embedding_model_id"] = req.embedding_model_id
    if req.embedding_model_version is not None:
        diff["embedding_model_version"] = req.embedding_model_version
    if req.parser_version is not None:
        diff["parser_version"] = req.parser_version
    if req.chunker_version is not None:
        diff["chunker_version"] = req.chunker_version
    if req.index_schema_version is not None:
        diff["index_schema_version"] = req.index_schema_version
    return diff


def build_shadow(
    request: IndexGenBuildShadowRequest,
    settings: Settings,
    app_state: AppState,
    embedder,
) -> dict[str, object]:
    target_versions = resolve_indexgen_target_versions(request)
    if not target_versions:
        raise ServiceError(
            ErrorCode.INDEXGEN_NO_VERSION_DIFF,
            "build-shadow requires at least one version field different from active.",
            {"kb_name": request.kb_name},
        )
    docs_dir = request.docs_dir or settings.manual_library.root_dir
    task = app_state.start_shadow_rebuild(
        docs_dir,
        request.kb_name,
        settings,
        target_versions=target_versions,
        embedder=embedder,
    )
    meta = app_state.get_generation_meta(request.kb_name)
    return {
        "kb_name": request.kb_name,
        "shadow_generation": meta.shadow_generation if meta else None,
        "task_id": task.task_id,
        "status": task.status,
    }


def cancel_shadow(request: IndexGenCancelShadowRequest, settings: Settings, app_state: AppState) -> dict[str, object]:
    return app_state.cancel_shadow_rebuild(request.kb_name, settings)


def swap_generation(request: IndexGenSwapRequest, settings: Settings, app_state: AppState) -> dict[str, object]:
    return app_state.swap_generation(request.kb_name, settings)


def retire_generation(request: IndexGenRetireRequest, settings: Settings, app_state: AppState) -> dict[str, object]:
    return app_state.retire_generation(request.kb_name, request.generation, settings, force=request.force)


def generation_status(kb_name: str, settings: Settings, app_state: AppState) -> dict[str, object]:
    from .indexgen import read_meta
    from pathlib import Path

    kb_root = Path(settings.storage.data_dir) / kb_name
    meta = app_state.get_generation_meta(kb_name) or read_meta(kb_root)
    if meta is None:
        raise ServiceError(
            ErrorCode.INDEXGEN_NO_SUCH_KB,
            "KB has no index.json.",
            {"kb_name": kb_name},
        )
    return meta.to_dict()
