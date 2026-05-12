from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hashlib
import sys
import time
import uuid

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
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
from .observability.metrics import configure_metrics, get_metrics, metrics_response_bytes
from .observability.tracing import configure_tracing, set_span_attributes, start_span
from .rate_limit.memory_sliding import InMemorySlidingWindowStore
from .state import AppState, load_kb
from .storage.json_anchor import JsonAnchorStore
from .types import GraphState
from .wave_searcher import wave_search

settings = load_config()
app_state = AppState()
embedder = None  # lazily created in lifespan to avoid import-time model download


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


class SearchRequest(BaseModel):
    question: str
    top_k: int | None = None
    source_k: int | None = None
    steps: int | None = None
    decay: float | None = None
    amplitude_cutoff: float | None = None
    aggregate: str | None = None
    kb_name: str = "default"


class RebuildRequest(BaseModel):
    docs_dir: str
    kb_name: str = "default"


class AnchorRequest(BaseModel):
    node_id: int
    label: str
    boost: float = Field(default=2.0, gt=0)
    propagation_boost: float = Field(default=1.0, gt=0)
    kb_name: str = "default"


class CacheClearRequest(BaseModel):
    kb_name: str | None = None


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
