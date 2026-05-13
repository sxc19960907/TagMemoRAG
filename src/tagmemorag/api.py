from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import sys
import time
from typing import cast
import uuid

from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from .anchor import AnchorSystem
from .auth.base import ApiKey
from .auth.config_store import ConfigAuthStore
from .auth.dependencies import ensure_kb_access, rate_limit_dep, require_scope
from .cache.lru_ttl import LRUTTLCache
from .config import Settings, load_config
from .embedder import create_embedder
from .errors import ErrorCode, KbNotLoadedError, ServiceError
from .logging_setup import configure_logging
from .manuals import metadata_from_node
from .manual_bulk_import import BulkImportMode, BulkUploadedFile, commit_bulk_import, preview_bulk_import
from .manual_library import (
    delete_manual,
    disable_manual,
    library_root,
    list_records,
    replace_manual_file,
    update_manual_metadata,
    upsert_manual,
    validate_metadata,
)
from .observability.metrics import configure_metrics, get_metrics, metrics_response_bytes
from .observability.tracing import configure_tracing, set_span_attributes, start_span
from .rate_limit.memory_sliding import InMemorySlidingWindowStore
from .state import AppState, load_kb, start_library_rebuild
from .storage.json_anchor import JsonAnchorStore
from .tag_suggestions import DEFAULT_LIMIT, suggest_tags
from .types import GraphState
from .wave_searcher import filter_node_ids, normalize_filters, wave_search

settings = load_config()
app_state = AppState()
embedder = None  # lazily created in lifespan to avoid import-time model download
WEB_DIR = Path(__file__).resolve().parent / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global embedder
    configure_logging(settings.logging.level, settings.logging.format)
    logger = structlog.get_logger()
    startup_t0 = time.perf_counter()
    logger.info("service_starting", config_path="config.yaml")
    app.state.settings = settings
    app.state.app_state = app_state
    configure_metrics(
        enabled=settings.observability.metrics.enabled,
        include_runtime=settings.observability.metrics.include_runtime,
    )
    configure_tracing(app, settings)
    if embedder is None:
        t0 = time.perf_counter()
        embedder = create_embedder(
            settings.model.name,
            settings.model.device,
            settings.model.batch_size,
            settings.model.dim,
            provider=settings.model.provider,
            base_url=settings.model.base_url,
            embeddings_url=settings.model.embeddings_url,
            api_key_env=settings.model.api_key_env,
            timeout_seconds=settings.model.timeout_seconds,
            dimensions=settings.model.dimensions,
            normalize=settings.model.normalize,
        )
        logger.info(
            "model_loaded",
            model_name=settings.model.name,
            provider=settings.model.provider,
            device=settings.model.device,
            duration_ms=round((time.perf_counter() - t0) * 1000.0, 3),
        )
    try:
        t0 = time.perf_counter()
        embedder.encode_query("warmup")
        app_state.mark_embedder_ready()
        get_metrics().set_embedder_ready(True)
        logger.info("model_warmed_up", duration_ms=round((time.perf_counter() - t0) * 1000.0, 3))
    except Exception as exc:
        logger.error("model_warmup_failed", error_type=type(exc).__name__, error_message=str(exc))
        sys.exit(1)
    app_state.auth_store = ConfigAuthStore.from_config(settings.auth)
    app_state.rate_limiter = InMemorySlidingWindowStore(settings.rate_limit.window_seconds)
    app_state.query_cache = (
        LRUTTLCache(settings.cache.max_entries, settings.cache.ttl_seconds) if settings.cache.enabled else None
    )
    _load_all_kbs(logger)
    get_metrics().set_kbs_loaded(len(app_state.kbs))
    if app_state.query_cache is not None:
        get_metrics().set_cache_entries(len(app_state.query_cache))
    get_metrics().record_startup_duration(time.perf_counter() - startup_t0)
    logger.info(
        "service_ready",
        kb_count=len(app_state.kbs),
        startup_duration_ms=round((time.perf_counter() - startup_t0) * 1000.0, 3),
    )
    try:
        yield
    finally:
        shutdown_t0 = time.perf_counter()
        logger.info("shutdown_started")
        app_state.begin_shutdown()
        drain_t0 = time.perf_counter()
        for kb_name in app_state.list_kbs():
            lock = app_state.lock_for(kb_name)
            await asyncio.to_thread(lock.acquire)
            lock.release()
        logger.info("rebuild_drained", wait_ms=round((time.perf_counter() - drain_t0) * 1000.0, 3))
        logger.info("shutdown_complete", total_ms=round((time.perf_counter() - shutdown_t0) * 1000.0, 3))


app = FastAPI(title="TagMemoRAG", lifespan=lifespan)
app.mount("/static/manual-library", StaticFiles(directory=str(WEB_DIR / "static")), name="manual-library-static")


class SearchRequest(BaseModel):
    question: str
    top_k: int | None = None
    source_k: int | None = None
    steps: int | None = None
    decay: float | None = None
    amplitude_cutoff: float | None = None
    aggregate: str | None = None
    kb_name: str = "default"
    filters: "SearchFilters | None" = None


class SearchFilters(BaseModel):
    manual_id: str | None = None
    brand: str | None = None
    product_category: str | None = None
    product_model: str | None = None
    language: str | None = None
    tags: list[str] = Field(default_factory=list)

    def to_filter_dict(self) -> dict[str, object]:
        return {
            "manual_id": self.manual_id,
            "brand": self.brand,
            "product_category": self.product_category,
            "product_model": self.product_model,
            "language": self.language,
            "tags": self.tags,
        }


class RebuildRequest(BaseModel):
    docs_dir: str
    kb_name: str = "default"


class ManualMetadataValidationRequest(BaseModel):
    kb_name: str = "default"
    metadata: dict[str, object]
    mode: str = "create"
    current_manual_id: str | None = None


class ManualMetadataUpdateRequest(BaseModel):
    kb_name: str = "default"
    metadata: dict[str, object]


class ManualTagSuggestRequest(BaseModel):
    kb_name: str = "default"
    metadata: dict[str, object]
    text_sample: str = Field(default="", max_length=4000)
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=24)


class ManualLibraryRebuildRequest(BaseModel):
    kb_name: str = "default"


class AnchorRequest(BaseModel):
    node_id: int
    label: str
    boost: float = Field(default=2.0, gt=0)
    propagation_boost: float = Field(default=1.0, gt=0)
    kb_name: str = "default"


class CacheClearRequest(BaseModel):
    kb_name: str | None = None


@app.get("/admin/manual-library")
def manual_library_admin(request: Request, kb_name: str = "default"):
    return templates.TemplateResponse(
        request,
        "manual_library.html",
        {
            "default_kb_name": kb_name or "default",
            "api_base_path": "",
            "auth_enabled": settings.auth.enabled,
        },
    )


def _status_for(code: ErrorCode) -> int:
    return {
        ErrorCode.KB_NOT_LOADED: 404,
        ErrorCode.ANCHOR_NOT_FOUND: 404,
        ErrorCode.REBUILD_IN_PROGRESS: 409,
        ErrorCode.INVALID_REQUEST: 400,
        ErrorCode.INVALID_INPUT: 400,
        ErrorCode.INVALID_CONFIG: 400,
        ErrorCode.STORAGE_SCHEMA_MISMATCH: 409,
        ErrorCode.STORAGE_LOAD_FAILED: 500,
        ErrorCode.REBUILD_FAILED: 500,
        ErrorCode.SHUTTING_DOWN: 503,
        ErrorCode.EMBEDDING_FAILED: 502,
        ErrorCode.UNAUTHORIZED: 401,
        ErrorCode.FORBIDDEN: 403,
        ErrorCode.RATE_LIMITED: 429,
        ErrorCode.INTERNAL: 500,
    }.get(code, 500)


def _load_all_kbs(logger) -> None:
    root = Path(settings.storage.data_dir)
    if not root.exists():
        logger.warning("kb_load_skipped", kb_name="default")
        return
    loaded_any = False
    for kb_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        if not (kb_dir / "meta.json").exists():
            continue
        try:
            with start_span("tagmemorag.kb.load", **{"tagmemorag.kb_name": kb_dir.name}):
                loaded = load_kb(kb_dir.name, settings)
            app_state.swap_kb(kb_dir.name, loaded)
            loaded_any = True
            logger.info(
                "kb_loaded",
                kb_name=loaded.kb_name,
                build_id=loaded.build_id,
                node_count=loaded.graph.number_of_nodes(),
            )
        except ServiceError as exc:
            logger.warning("kb_load_failed", kb_name=kb_dir.name, code=exc.code.value, message=exc.message)
    if not loaded_any:
        try:
            with start_span("tagmemorag.kb.load", **{"tagmemorag.kb_name": "default"}):
                loaded = load_kb("default", settings)
            app_state.swap_kb("default", loaded)
            logger.info("kb_loaded", kb_name=loaded.kb_name, build_id=loaded.build_id)
        except KbNotLoadedError:
            logger.warning("kb_load_skipped", kb_name="default")


def _normalize_question(question: str) -> str:
    return " ".join(question.strip().split())


def _search_param_values(request: SearchRequest) -> dict[str, object]:
    return {
        "top_k": request.top_k or settings.search.top_k,
        "source_k": request.source_k or settings.search.source_k,
        "steps": request.steps if request.steps is not None else settings.search.steps,
        "decay": request.decay if request.decay is not None else settings.search.decay,
        "amplitude_cutoff": request.amplitude_cutoff
        if request.amplitude_cutoff is not None
        else settings.search.amplitude_cutoff,
        "aggregate": request.aggregate or settings.search.aggregate,
    }


def _compute_cache_key(request: SearchRequest, state: GraphState) -> str:
    params = _search_param_values(request)
    filter_dict = request.filters.to_filter_dict() if request.filters else {}
    canonical_filters = normalize_filters(filter_dict)
    parts = [
        request.kb_name,
        state.build_id,
        str(state.anchors_version),
        _normalize_question(request.question),
        str(params["top_k"]),
        str(params["source_k"]),
        str(params["steps"]),
        str(params["decay"]),
        str(params["amplitude_cutoff"]),
        str(params["aggregate"]),
        json.dumps(canonical_filters, sort_keys=True, separators=(",", ":")),
    ]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    request.app.state.settings = settings
    request.app.state.app_state = app_state
    trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
    request.state.trace_id = trace_id
    clear_contextvars()
    bind_contextvars(trace_id=trace_id, path=request.url.path, method=request.method)
    try:
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response
    finally:
        clear_contextvars()


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    metrics_path = settings.observability.metrics.path
    if settings.observability.metrics.enabled and request.url.path == metrics_path:
        return _metrics_response()
    if not settings.observability.metrics.enabled:
        return await call_next(request)
    t0 = time.perf_counter()
    status_code = "500"
    route = request.url.path
    try:
        response = await call_next(request)
        status_code = str(response.status_code)
        route = _route_template(request)
        return response
    finally:
        get_metrics().record_http_request(
            method=request.method,
            route=route,
            status_code=status_code,
            duration=time.perf_counter() - t0,
        )


@app.middleware("http")
async def rate_limit_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    result = getattr(request.state, "rate_limit", None)
    if result is not None:
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(result.reset_epoch)
        if not result.allowed:
            response.headers["Retry-After"] = str(result.retry_after_seconds)
    return response


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return str(getattr(route, "path", request.url.path))


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError):
    get_metrics().record_http_error(
        route=_route_template(request),
        status_code=_status_for(exc.code),
        error_code=exc.code.value,
    )
    structlog.get_logger().warning(
        "request_error",
        code=exc.code.value,
        status=_status_for(exc.code),
        exception_type=type(exc).__name__,
    )
    return JSONResponse(status_code=_status_for(exc.code), content=exc.to_dict())


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    get_metrics().record_http_error(
        route=_route_template(request),
        status_code=500,
        error_code=ErrorCode.INTERNAL.value,
    )
    structlog.get_logger().error(
        "request_error",
        code=ErrorCode.INTERNAL.value,
        status=500,
        exception_type=type(exc).__name__,
    )
    wrapped = ServiceError(
        ErrorCode.INTERNAL,
        "Internal server error.",
        {"type": type(exc).__name__, "message": str(exc)},
    )
    return JSONResponse(status_code=500, content=wrapped.to_dict())


@app.get("/health", include_in_schema=False)
def health():
    return PlainTextResponse("ok", status_code=200)


@app.get("/ready", include_in_schema=False)
def ready():
    if app_state.is_shutting_down:
        return PlainTextResponse("shutting down", status_code=503)
    if not app_state.embedder_ready:
        return PlainTextResponse("embedder not ready", status_code=503)
    if app_state.current is None:
        return PlainTextResponse("kb not loaded", status_code=503)
    return PlainTextResponse("ok", status_code=200)


@app.get("/metrics", include_in_schema=False)
def metrics_endpoint():
    if not settings.observability.metrics.enabled:
        return PlainTextResponse("metrics disabled", status_code=404)
    if settings.observability.metrics.path != "/metrics":
        return PlainTextResponse("metrics not found", status_code=404)
    return _metrics_response()


def _metrics_response() -> Response:
    body, content_type = metrics_response_bytes()
    return Response(content=body, media_type=content_type)


@app.post("/search")
def search(
    request: SearchRequest,
    http_request: Request,
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, request.kb_name)
    state = app_state.get_current(request.kb_name)
    t0 = time.perf_counter()
    try:
        span_attrs = {
            "tagmemorag.kb_name": state.kb_name,
            "tagmemorag.build_id": state.build_id,
            "tagmemorag.query_len": len(request.question),
            "tagmemorag.top_k": request.top_k or settings.search.top_k,
            "tagmemorag.x_trace_id": getattr(http_request.state, "trace_id", ""),
        }
        search_span = start_span("tagmemorag.search", **span_attrs)
        with search_span:
            return _search_impl(request, http_request, state, t0)
    except ServiceError as exc:
        get_metrics().record_search(
            kb_name=request.kb_name,
            cache_status="none",
            outcome="error",
            duration=time.perf_counter() - t0,
            error_code=exc.code.value,
        )
        set_span_attributes(**{"tagmemorag.error_code": exc.code.value})
        raise


def _search_impl(request: SearchRequest, http_request: Request, state: GraphState, t0: float):
    cache_status = "disabled"
    cache_key = _compute_cache_key(request, state)
    cache = app_state.query_cache if settings.cache.enabled else None
    with start_span("tagmemorag.search.cache", **{"tagmemorag.kb_name": state.kb_name}):
        cached = cache.get(cache_key) if cache is not None else None
        cache_status = "hit" if cached is not None else ("miss" if cache is not None else "disabled")
        set_span_attributes(**{"tagmemorag.cache_status": cache_status})
    get_metrics().record_cache_operation(operation="get", outcome=cache_status)
    if cached is not None:
        search_time_ms = (time.perf_counter() - t0) * 1000.0
        trace_id = str(getattr(http_request.state, "trace_id", ""))
        payload = {**cached, "trace_id": trace_id, "search_time_ms": round(search_time_ms, 3), "cache": "hit"}
        result_count = len(payload.get("results", []))
        get_metrics().record_search(
            kb_name=state.kb_name,
            cache_status="hit",
            outcome="success",
            duration=time.perf_counter() - t0,
            result_count=result_count,
        )
        set_span_attributes(
            **{
                "tagmemorag.cache_status": "hit",
                "tagmemorag.result_count": result_count,
            }
        )
        structlog.get_logger().info(
            "search",
            kb_name=state.kb_name,
            build_id=state.build_id,
            query_len=len(request.question),
            top_k=request.top_k or settings.search.top_k,
            result_count=result_count,
            latency_ms=round(search_time_ms, 3),
            cache_status="hit",
        )
        return payload
    emb_t0 = time.perf_counter()
    try:
        with start_span("tagmemorag.search.embedding", **{"tagmemorag.kb_name": state.kb_name}):
            query_vec = embedder.encode_query(request.question)
        get_metrics().record_embedding(operation="query", outcome="success", duration=time.perf_counter() - emb_t0)
    except Exception:
        get_metrics().record_embedding(operation="query", outcome="error", duration=time.perf_counter() - emb_t0)
        raise
    params = _search_param_values(request)
    aggregate = str(params["aggregate"])
    if aggregate not in {"max", "sum"}:
        raise ServiceError(
            ErrorCode.INVALID_INPUT,
            "aggregate must be 'max' or 'sum'.",
            {"aggregate": aggregate},
        )
    with start_span("tagmemorag.search.wave", **{"tagmemorag.kb_name": state.kb_name}):
        filter_dict = request.filters.to_filter_dict() if request.filters else {}
        eligible_node_ids = filter_node_ids(state.graph, filter_dict)
        results = wave_search(
            query_vec,
            state.graph,
            state.vectors,
            state.anchors,
            top_k=int(params["top_k"]),
            source_k=int(params["source_k"]),
            steps=int(params["steps"]),
            decay=float(params["decay"]),
            amplitude_cutoff=float(params["amplitude_cutoff"]),
            aggregate=aggregate,  # type: ignore[arg-type]
            eligible_node_ids=eligible_node_ids,
            filters=filter_dict,
            metadata_field_boost=settings.search.metadata_field_boost,
            tag_boost=settings.search.tag_boost,
        )
    search_time_ms = (time.perf_counter() - t0) * 1000.0
    trace_id = str(getattr(http_request.state, "trace_id", ""))
    structlog.get_logger().info(
        "search",
        kb_name=state.kb_name,
        build_id=state.build_id,
        query_len=len(request.question),
        top_k=request.top_k or settings.search.top_k,
        result_count=len(results),
        latency_ms=round(search_time_ms, 3),
        cache_status="miss",
    )
    get_metrics().record_search(
        kb_name=state.kb_name,
        cache_status=cache_status,
        outcome="success",
        duration=time.perf_counter() - t0,
        result_count=len(results),
    )
    set_span_attributes(
        **{
            "tagmemorag.cache_status": cache_status,
            "tagmemorag.result_count": len(results),
        }
    )
    payload = {
        "build_id": state.build_id,
        "kb_name": state.kb_name,
        "trace_id": trace_id,
        "results": [r.to_dict() for r in results],
        "search_time_ms": round(search_time_ms, 3),
        "cache": "miss",
    }
    if cache is not None:
        cache.set(cache_key, {k: v for k, v in payload.items() if k not in {"trace_id", "search_time_ms", "cache"}}, kb_name=request.kb_name)
        get_metrics().record_cache_operation(operation="set", outcome="success")
        get_metrics().set_cache_entries(len(cache))
    return payload


@app.post("/rebuild", status_code=202)
def rebuild(
    request: RebuildRequest,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, request.kb_name)
    task = app_state.start_rebuild(request.docs_dir, request.kb_name, settings, embedder=embedder)
    return task.to_dict()


@app.get("/rebuild/{task_id}")
def get_rebuild(task_id: str, _api_key: ApiKey = Depends(require_scope("rebuild")), _: None = Depends(rate_limit_dep)):
    task = app_state.rebuild_tasks.get(task_id)
    if not task:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Rebuild task not found.", {"task_id": task_id})
    return task.to_dict()


@app.post("/anchor")
def add_anchor(
    request: AnchorRequest,
    api_key: ApiKey = Depends(require_scope("anchor.write")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, request.kb_name)
    state = app_state.get_current(request.kb_name)
    store = JsonAnchorStore(f"{settings.storage.data_dir}/{request.kb_name}/anchors.json")
    anchor = AnchorSystem(state, store).add(request.node_id, request.label, request.boost, request.propagation_boost)
    structlog.get_logger().info("anchor_created", anchor_key=anchor.anchor_key, label=anchor.label)
    return anchor.to_dict()


@app.delete("/anchor/{anchor_key}")
def delete_anchor(
    anchor_key: str,
    kb_name: str = "default",
    api_key: ApiKey = Depends(require_scope("anchor.write")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, kb_name)
    state = app_state.get_current(kb_name)
    store = JsonAnchorStore(f"{settings.storage.data_dir}/{kb_name}/anchors.json")
    AnchorSystem(state, store).delete(anchor_key)
    structlog.get_logger().info("anchor_deleted", anchor_key=anchor_key)
    return {"status": "deleted", "anchor_key": anchor_key}


@app.get("/anchor")
def list_anchor(
    kb_name: str = "default",
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, kb_name)
    state = app_state.get_current(kb_name)
    return {"anchors": [anchor.to_dict() for anchor in state.anchors.values()]}


@app.get("/graph_info")
def graph_info(
    kb_name: str = "default",
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, kb_name)
    state = app_state.get_current(kb_name)
    return {
        "kb_name": state.kb_name,
        "build_id": state.build_id,
        "node_count": state.graph.number_of_nodes(),
        "edge_count": state.graph.number_of_edges(),
        "anchors_version": state.anchors_version,
        "meta": state.meta,
        "unresolved_anchors": [anchor.to_dict() for anchor in state.unresolved_anchors],
    }


@app.get("/manuals")
def list_manuals(
    kb_name: str = "default",
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
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
                "tags": list(metadata.get("tags", [])) if isinstance(metadata.get("tags", []), list) else [],
                "chunk_count": 0,
            },
        )
        entry["chunk_count"] = int(entry["chunk_count"]) + 1
        for field in ("brand", "product_category", "product_model", "language"):
            value = str(metadata.get(field, "")).strip()
            if value:
                facets[field].add(value)
        tags = metadata.get("tags", [])
        if isinstance(tags, list):
            facets["tags"].update(str(tag) for tag in tags if str(tag).strip())
    return {
        "kb_name": state.kb_name,
        "build_id": state.build_id,
        "manuals": sorted(manuals.values(), key=lambda item: str(item["manual_id"])),
        "facets": {key: sorted(values) for key, values in facets.items()},
    }


@app.post("/manuals/validate")
def validate_manual_metadata(
    request: ManualMetadataValidationRequest,
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, request.kb_name)
    if request.mode not in {"create", "update", "upsert"}:
        raise ServiceError(ErrorCode.INVALID_INPUT, "mode must be create, update, or upsert.", {"mode": request.mode})
    result = validate_metadata(
        request.kb_name,
        dict(request.metadata),
        settings,
        mode=request.mode,  # type: ignore[arg-type]
        current_manual_id=request.current_manual_id,
    )
    return result.to_dict()


@app.post("/manuals/tags/suggest")
def suggest_manual_tags(
    request: ManualTagSuggestRequest,
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, request.kb_name)
    graph_state = app_state.kbs.get(request.kb_name)
    records = list_records(request.kb_name, settings, graph_state=graph_state)
    suggestions, existing_tags = suggest_tags(
        dict(request.metadata),
        records=records,
        graph_state=graph_state,
        text_sample=request.text_sample,
        limit=request.limit,
    )
    return {
        "kb_name": request.kb_name,
        "suggestions": [suggestion.to_dict() for suggestion in suggestions],
        "existing_tags": existing_tags,
    }


@app.post("/manuals")
async def upload_manual(
    kb_name: str = Form("default"),
    metadata: str = Form(...),
    overwrite: bool = Form(False),
    trigger_rebuild: bool = Form(False),
    file: UploadFile = File(...),
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, kb_name)
    metadata_obj = _parse_metadata_form(metadata)
    content = await file.read()
    record = upsert_manual(kb_name, metadata_obj, content, settings, overwrite=overwrite or settings.manual_library.allow_overwrite)
    task = start_library_rebuild(app_state, kb_name, settings, embedder=embedder) if trigger_rebuild else None
    structlog.get_logger().info("manual_library_mutation", kb_name=kb_name, manual_id=record.manual_id, action="upsert", status=record.status)
    return {"record": record.to_dict(), "rebuild_required": True, "rebuild_task": task.to_dict() if task else None}


@app.post("/manual-library/bulk/preview")
async def preview_manual_bulk_import(
    kb_name: str = Form("default"),
    metadata_format: str = Form("json"),
    metadata: str = Form(""),
    mode: str = Form("create_only"),
    overwrite: bool = Form(False),
    metadata_file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, kb_name)
    metadata_text = await _metadata_text_from_bulk_form(metadata, metadata_file)
    uploaded = await _bulk_uploaded_files(files)
    preview = preview_bulk_import(
        kb_name,
        metadata_text,
        metadata_format,
        uploaded,
        settings,
        mode=_parse_bulk_mode(mode),
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


@app.post("/manual-library/bulk/import")
async def import_manual_bulk(
    kb_name: str = Form("default"),
    metadata_format: str = Form("json"),
    metadata: str = Form(""),
    mode: str = Form("create_only"),
    overwrite: bool = Form(False),
    selected_rows: str = Form(""),
    trigger_rebuild: bool = Form(False),
    metadata_file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, kb_name)
    metadata_text = await _metadata_text_from_bulk_form(metadata, metadata_file)
    uploaded = await _bulk_uploaded_files(files)
    result = commit_bulk_import(
        kb_name,
        metadata_text,
        metadata_format,
        uploaded,
        settings,
        mode=_parse_bulk_mode(mode),
        overwrite=overwrite,
        selected_rows=_parse_selected_rows(selected_rows),
    )
    task = start_library_rebuild(app_state, kb_name, settings, embedder=embedder) if trigger_rebuild and result.imported_count else None
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
    body["rebuild_task"] = task.to_dict() if task else None
    return body


@app.patch("/manuals/{manual_id}/metadata")
def patch_manual_metadata(
    manual_id: str,
    request: ManualMetadataUpdateRequest,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
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


@app.put("/manuals/{manual_id}/file")
async def put_manual_file(
    manual_id: str,
    kb_name: str = Form("default"),
    file: UploadFile = File(...),
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, kb_name)
    record = replace_manual_file(kb_name, manual_id, await file.read(), settings)
    structlog.get_logger().info("manual_library_mutation", kb_name=kb_name, manual_id=manual_id, action="file_replace", status=record.status)
    return {"record": record.to_dict(), "rebuild_required": True}


@app.delete("/manuals/{manual_id}")
def remove_manual(
    manual_id: str,
    kb_name: str = "default",
    hard: bool = False,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
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


@app.get("/manual-library")
def list_manual_library(
    kb_name: str = "default",
    manual_id: str | None = None,
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, kb_name)
    graph_state = app_state.kbs.get(kb_name)
    records = list_records(kb_name, settings, graph_state=graph_state)
    if manual_id is not None:
        records = [record for record in records if record.manual_id == manual_id]
        if not records:
            raise ServiceError(ErrorCode.INVALID_REQUEST, "Manual not found.", {"manual_id": manual_id, "kb_name": kb_name})
    return {
        "kb_name": kb_name,
        "library_root": str(library_root(kb_name, settings)),
        "manuals": [record.to_dict() for record in records],
    }


@app.post("/manual-library/rebuild", status_code=202)
def rebuild_manual_library(
    request: ManualLibraryRebuildRequest,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, request.kb_name)
    task = start_library_rebuild(app_state, request.kb_name, settings, embedder=embedder)
    return task.to_dict()


@app.get("/kb")
def list_kbs(api_key: ApiKey = Depends(require_scope("search")), _: None = Depends(rate_limit_dep)):
    entries = []
    running = {task.kb_name for task in app_state.rebuild_tasks.values() if task.status == "running"}
    for kb_name in app_state.list_kbs():
        if not api_key.allows_kb(kb_name):
            continue
        state = app_state.get_kb(kb_name)
        entries.append(
            {
                "kb_name": state.kb_name,
                "build_id": state.build_id,
                "node_count": state.graph.number_of_nodes(),
                "anchors_version": state.anchors_version,
                "status": "rebuilding" if kb_name in running else "ready",
            }
        )
    return {"kbs": entries}


@app.post("/admin/cache/clear")
def clear_cache(request: CacheClearRequest, _api_key: ApiKey = Depends(require_scope("admin"))):
    with start_span("tagmemorag.cache.clear", **{"tagmemorag.kb_name": request.kb_name or "all"}):
        if app_state.query_cache is None:
            get_metrics().record_cache_operation(operation="clear", outcome="disabled")
            return {"cleared_count": 0}
        cleared = app_state.query_cache.clear(request.kb_name)
        get_metrics().record_cache_operation(operation="clear", outcome="success")
        get_metrics().set_cache_entries(len(app_state.query_cache))
        structlog.get_logger().info("cache_cleared", kb_name=request.kb_name, cleared_count=cleared)
        return {"cleared_count": cleared}


def _parse_metadata_form(metadata: str) -> dict[str, object]:
    try:
        parsed = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise ServiceError(ErrorCode.INVALID_INPUT, "metadata must be valid JSON.", {"error": str(exc)}) from exc
    if not isinstance(parsed, dict):
        raise ServiceError(ErrorCode.INVALID_INPUT, "metadata must be a JSON object.")
    return parsed


async def _metadata_text_from_bulk_form(metadata: str, metadata_file: UploadFile | None) -> str:
    if metadata_file is not None:
        content = await metadata_file.read()
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ServiceError(ErrorCode.INVALID_INPUT, "metadata_file must be UTF-8 text.", {"error": str(exc)}) from exc
    if not metadata.strip():
        raise ServiceError(ErrorCode.INVALID_INPUT, "metadata or metadata_file is required.")
    return metadata


async def _bulk_uploaded_files(files: list[UploadFile] | None) -> list[BulkUploadedFile]:
    uploaded: list[BulkUploadedFile] = []
    for file in files or []:
        if not file.filename:
            continue
        uploaded.append(BulkUploadedFile(filename=file.filename, content=await file.read()))
    return uploaded


def _parse_selected_rows(selected_rows: str) -> set[int] | None:
    if not selected_rows.strip():
        return None
    try:
        parsed = json.loads(selected_rows)
    except json.JSONDecodeError as exc:
        raise ServiceError(ErrorCode.INVALID_INPUT, "selected_rows must be a JSON array of row numbers.", {"error": str(exc)}) from exc
    if not isinstance(parsed, list):
        raise ServiceError(ErrorCode.INVALID_INPUT, "selected_rows must be a JSON array of row numbers.")
    rows: set[int] = set()
    for item in parsed:
        try:
            rows.add(int(item))
        except (TypeError, ValueError) as exc:
            raise ServiceError(ErrorCode.INVALID_INPUT, "selected_rows must contain only row numbers.", {"value": item}) from exc
    return rows


def _parse_bulk_mode(mode: str) -> BulkImportMode:
    if mode not in {"create_only", "upsert", "dry_run"}:
        raise ServiceError(ErrorCode.INVALID_INPUT, "mode must be create_only, upsert, or dry_run.", {"mode": mode})
    return cast(BulkImportMode, mode)
