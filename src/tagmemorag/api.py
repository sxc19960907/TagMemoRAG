from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import sys
import time
import uuid

from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from .anchor import AnchorSystem
from .auth.base import ApiKey
from .auth.config_store import ConfigAuthStore
from .auth.dependencies import ensure_kb_access, rate_limit_dep, require_scope
from .auth.keygen import generate_api_key_material
from .cache.lru_ttl import LRUTTLCache
from . import api_admin, api_eval_report, api_feedback, api_manual_routes, api_search
from .api_models import (
    AccessKeyGenerateRequest,
    AgenticRequestOverrides,
    AnchorRequest,
    AnswerRequest,
    BudgetSpec,
    CacheClearRequest,
    FeedbackPromoteRequest,
    FeedbackReviewRequest,
    FeedbackSubmitRequest,
    GhostTagSpec,
    IndexGenBuildShadowRequest,
    IndexGenCancelShadowRequest,
    IndexGenRetireRequest,
    IndexGenSwapRequest,
    ManualLibraryRebuildRequest,
    ManualMetadataUpdateRequest,
    ManualMetadataValidationRequest,
    ManualTagSuggestRequest,
    QaAnswerRequest,
    QaConversationTurn,
    RebuildRequest,
    RetrieveRequest,
    SearchFilters,
    SearchRequest,
    TagPolicyUpdateRequest,
    TagRewriteRequest,
)
from .api_manual import (
    resolved_filter_dict,
)
from .api_qa import qa_clarification_response, qa_not_ready_response, route_qa_question
from .config import Settings, load_config
from .document_assets import create_asset_store, load_asset_manifest
from .embedder import create_embedder
from .errors import ErrorCode, KbNotLoadedError, ServiceError
from .logging_setup import configure_logging
from .observability.metrics import configure_metrics, get_metrics
from .observability.tracing import configure_tracing, set_span_attributes, start_span
from .rate_limit.memory_sliding import InMemorySlidingWindowStore
from .rebuild_queue import RebuildQueue
from .search_runtime import execute_search
from .state import AppState, load_kb
from .storage.json_anchor import JsonAnchorStore
from .types import GraphState

settings = load_config()
app_state = AppState()
embedder = None  # lazily created in lifespan to avoid import-time model download
rebuild_queue: RebuildQueue | None = None
WEB_DIR = Path(__file__).resolve().parent / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
QA_ANSWER_TOP_K = 2
QA_ANSWER_SOURCE_K = 4


@asynccontextmanager
async def lifespan(app: FastAPI):
    global embedder, rebuild_queue
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
    if settings.manual_library.rebuild_queue_enabled:
        rebuild_queue = RebuildQueue(app_state, settings, embedder=embedder)
        app.state.rebuild_queue = rebuild_queue
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
        if rebuild_queue is not None:
            rebuild_queue.shutdown()
        drain_t0 = time.perf_counter()
        for kb_name in app_state.list_kbs():
            lock = app_state.lock_for(kb_name)
            await asyncio.to_thread(lock.acquire)
            lock.release()
        logger.info("rebuild_drained", wait_ms=round((time.perf_counter() - drain_t0) * 1000.0, 3))
        logger.info("shutdown_complete", total_ms=round((time.perf_counter() - shutdown_t0) * 1000.0, 3))


app = FastAPI(title="TagMemoRAG", lifespan=lifespan)
app.mount("/static/manual-library", StaticFiles(directory=str(WEB_DIR / "static")), name="manual-library-static")


@app.get("/", include_in_schema=False)
def browser_entrypoint():
    return RedirectResponse(url="/admin/rag-workbench?kb_name=default", status_code=303)


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


@app.get("/admin/retrieval-quality")
def retrieval_quality_admin(request: Request, kb_name: str = "default"):
    return templates.TemplateResponse(
        request,
        "retrieval_quality.html",
        {
            "default_kb_name": kb_name or "default",
            "api_base_path": "",
            "auth_enabled": settings.auth.enabled,
        },
    )


@app.get("/admin/eval-report")
def eval_report_admin(request: Request, kb_name: str = "default", report_path: str = ""):
    return templates.TemplateResponse(
        request,
        "eval_report.html",
        {
            "default_kb_name": kb_name or "default",
            "default_report_path": report_path or "",
            "api_base_path": "",
            "auth_enabled": settings.auth.enabled,
        },
    )


@app.get("/admin/rag-workbench")
def rag_workbench_admin(request: Request, kb_name: str = "default"):
    return templates.TemplateResponse(
        request,
        "rag_workbench.html",
        {
            "default_kb_name": kb_name or "default",
            "api_base_path": "",
            "auth_enabled": settings.auth.enabled,
        },
    )


@app.get("/admin/people")
def people_admin(request: Request, kb_name: str = "default"):
    return templates.TemplateResponse(
        request,
        "people_admin.html",
        {
            "default_kb_name": kb_name or "default",
            "api_base_path": "",
            "auth_enabled": settings.auth.enabled,
        },
    )


@app.get("/qa")
def qa_page(request: Request, kb_name: str = "default"):
    return templates.TemplateResponse(
        request,
        "qa_page.html",
        {
            "default_kb_name": kb_name or "default",
            "api_base_path": "",
            "auth_enabled": settings.auth.enabled,
        },
    )


def _safe_access_key(api_key: ApiKey) -> dict[str, object]:
    scopes = sorted(api_key.scopes)
    revoked = bool(api_key.revoked)
    return {
        "id": api_key.id,
        "label": api_key.label,
        "scopes": scopes,
        "kb_allowlist": list(api_key.kb_allowlist),
        "rate_limit_per_minute": api_key.rate_limit_per_minute,
        "created_at": api_key.created_at,
        "last_used_at": api_key.last_used_at,
        "revoked": revoked,
        "status": "revoked" if revoked else "active",
        "is_admin": "admin" in api_key.scopes,
    }


def _people_access_summary() -> dict[str, object]:
    store = app_state.auth_store
    keys = [_safe_access_key(api_key) for api_key in store.list_keys()] if store is not None else []
    active_keys = sum(1 for item in keys if item["status"] == "active")
    revoked_keys = sum(1 for item in keys if item["status"] == "revoked")
    admin_keys = sum(1 for item in keys if item["is_admin"] is True)
    return {
        "schema_version": "people_access.v1",
        "auth_enabled": settings.auth.enabled,
        "backend": settings.auth.backend,
        "global_max_rate_limit_per_minute": settings.auth.global_max_rate_limit_per_minute,
        "public_paths": list(settings.auth.public_paths),
        "keys": keys,
        "summary": {
            "total_keys": len(keys),
            "active_keys": active_keys,
            "revoked_keys": revoked_keys,
            "admin_keys": admin_keys,
        },
    }


@app.get("/admin/people/access-summary")
def get_people_access_summary(
    _: ApiKey = Depends(require_scope("admin")),
    __: None = Depends(rate_limit_dep),
):
    return _people_access_summary()


@app.post("/admin/people/access-keys/generate")
def generate_people_access_key(
    request: AccessKeyGenerateRequest,
    _: ApiKey = Depends(require_scope("admin")),
    __: None = Depends(rate_limit_dep),
):
    return generate_api_key_material(
        key_id=request.id,
        label=request.label,
        scopes=request.scopes,
        kb_allowlist=request.kb_allowlist,
        rate_limit_per_minute=request.rate_limit_per_minute,
        prefix=request.prefix,
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


def _sync_api_search() -> None:
    answer_override = None if _answer_generator is _default_answer_generator else _answer_generator
    api_search.configure(
        settings,
        app_state,
        embedder,
        runtime_execute_search=execute_search,
        runtime_answer_generator=answer_override,
    )


def _normalize_question(question: str) -> str:
    _sync_api_search()
    return api_search.normalize_question_for_cache(question)


def _trim_context_text(value: str | None, limit: int) -> str:
    _sync_api_search()
    return api_search.trim_context_text_for_api(value, limit)


def _qa_contextual_question(request: QaAnswerRequest) -> str:
    _sync_api_search()
    return api_search.qa_contextual_question(request)


def _qa_context_meta(request: QaAnswerRequest) -> dict[str, object]:
    _sync_api_search()
    return api_search.qa_context_meta(request)


def _compute_cache_key(request: SearchRequest, state: GraphState) -> str:
    _sync_api_search()
    return api_search.compute_cache_key(request, state)


def _compute_search_id(request: SearchRequest, state: GraphState, trace_id: str) -> str:
    _sync_api_search()
    return api_search.compute_search_id(request, state, trace_id)


def _search_impl(request: SearchRequest, http_request: Request, state: GraphState, t0: float):
    _sync_api_search()
    return api_search.search_impl(request, http_request, state, t0)


def _retrieve_impl(request: RetrieveRequest, http_request: Request, state: GraphState, t0: float):
    _sync_api_search()
    return api_search.retrieve_impl(request, http_request, state, t0)


def _build_answer_response(request: AnswerRequest, retrieve_payload: dict) -> dict:
    _sync_api_search()
    return api_search.build_answer_response(request, retrieve_payload)


_ANSWER_GENERATOR_CACHE = api_search._ANSWER_GENERATOR_CACHE
_RERANK_DISPATCHER_CACHE = api_search._RERANK_DISPATCHER_CACHE


def _default_answer_generator():
    return api_search.answer_generator()


_answer_generator = _default_answer_generator




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
    return api_admin.health_response()


@app.get("/ready", include_in_schema=False)
def ready():
    return api_admin.ready_response(app_state)


@app.get("/metrics", include_in_schema=False)
def metrics_endpoint():
    return api_admin.metrics_endpoint_response(settings)


def _metrics_response() -> Response:
    return api_admin.metrics_response()


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


@app.post("/retrieve")
def retrieve(
    request: RetrieveRequest,
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
        with start_span("tagmemorag.retrieve", **span_attrs):
            return _retrieve_impl(request, http_request, state, t0)
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


@app.post("/answer")
def answer(
    request: AnswerRequest,
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
        with start_span("tagmemorag.answer", **span_attrs):
            retrieve_payload = _retrieve_impl(request, http_request, state, t0)
            return _build_answer_response(request, retrieve_payload)
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


@app.post("/qa/answer")
def qa_answer(
    request: QaAnswerRequest,
    http_request: Request,
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    effective_question = _qa_contextual_question(request)
    context_meta = _qa_context_meta(request)
    route = route_qa_question(effective_question, api_key, app_state)
    if route["kind"] == "not_ready":
        payload = qa_not_ready_response(route)
        payload["context"] = context_meta
        return payload
    if route["kind"] == "clarification":
        payload = qa_clarification_response(request, route)
        payload["context"] = context_meta
        return payload

    kb_name = str(route["kb_name"])
    answer_request = AnswerRequest(
        question=effective_question,
        kb_name=kb_name,
        top_k=QA_ANSWER_TOP_K,
        source_k=QA_ANSWER_SOURCE_K,
        mode="classic",
        include_retrieve=request.include_retrieve,
    )
    ensure_kb_access(api_key, kb_name)
    state = app_state.get_current(kb_name)
    t0 = time.perf_counter()
    try:
        span_attrs = {
            "tagmemorag.kb_name": state.kb_name,
            "tagmemorag.build_id": state.build_id,
            "tagmemorag.query_len": len(effective_question),
            "tagmemorag.top_k": answer_request.top_k or settings.search.top_k,
            "tagmemorag.x_trace_id": getattr(http_request.state, "trace_id", ""),
        }
        with start_span("tagmemorag.qa.answer", **span_attrs):
            retrieve_payload = _retrieve_impl(answer_request, http_request, state, t0)
            payload = _build_answer_response(answer_request, retrieve_payload)
            payload["route"] = {
                "kind": "answered",
                "kb_name": state.kb_name,
                "reason": route.get("reason", "single_kb"),
            }
            payload["question"] = request.question
            payload["context"] = context_meta
            return payload
    except ServiceError as exc:
        get_metrics().record_search(
            kb_name=kb_name,
            cache_status="none",
            outcome="error",
            duration=time.perf_counter() - t0,
            error_code=exc.code.value,
        )
        set_span_attributes(**{"tagmemorag.error_code": exc.code.value})
        raise



@app.post("/rebuild", status_code=202)
def rebuild(
    request: RebuildRequest,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, request.kb_name)
    task = app_state.start_rebuild(request.docs_dir, request.kb_name, settings, embedder=embedder)
    return task.to_dict()


@app.post("/search/feedback")
def submit_search_feedback(
    request: FeedbackSubmitRequest,
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    return api_feedback.submit_feedback(request, api_key, settings, kind="search")


@app.post("/retrieve/feedback")
def submit_retrieve_feedback(
    request: FeedbackSubmitRequest,
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    return api_feedback.submit_feedback(request, api_key, settings, kind="retrieve")


@app.get("/search/feedback")
def get_search_feedback(
    kb_name: str = "default",
    status: str | None = None,
    outcome: str | None = None,
    query: str | None = None,
    limit: int = 50,
    api_key: ApiKey = Depends(require_scope("admin")),
    _: None = Depends(rate_limit_dep),
):
    return api_feedback.list_search_feedback(
        kb_name,
        api_key,
        settings,
        status=status,
        outcome=outcome,
        query=query,
        limit=limit,
    )


@app.patch("/search/feedback/{feedback_id}")
def patch_search_feedback(
    feedback_id: str,
    request: FeedbackReviewRequest,
    api_key: ApiKey = Depends(require_scope("admin")),
    _: None = Depends(rate_limit_dep),
):
    return api_feedback.review_search_feedback(feedback_id, request, api_key, settings)


@app.post("/search/feedback/promote/preview")
def preview_search_feedback_promotion(
    request: FeedbackPromoteRequest,
    api_key: ApiKey = Depends(require_scope("admin")),
    _: None = Depends(rate_limit_dep),
):
    return api_feedback.preview_search_feedback(request, api_key, settings)


@app.post("/search/feedback/promote")
def promote_search_feedback(
    request: FeedbackPromoteRequest,
    api_key: ApiKey = Depends(require_scope("admin")),
    _: None = Depends(rate_limit_dep),
):
    return api_feedback.promote_search_feedback(request, api_key, settings)


@app.get("/eval/report")
def get_eval_report(
    path: str,
    _api_key: ApiKey = Depends(require_scope("admin")),
    _: None = Depends(rate_limit_dep),
):
    return api_eval_report.load_eval_report_view(path)


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


@app.get("/assets/{asset_id}")
def get_document_asset(
    asset_id: str,
    kb_name: str = "default",
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, kb_name)
    manifest = load_asset_manifest(kb_name, settings)
    asset = manifest.assets.get(asset_id)
    if asset is None or asset.status != "ready":
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Document asset not found.", {"asset_id": asset_id, "kb_name": kb_name})
    if asset.kb_name != kb_name:
        raise ServiceError(ErrorCode.FORBIDDEN, "Document asset belongs to a different KB.", {"asset_id": asset_id, "kb_name": kb_name})
    store = create_asset_store(settings)
    if asset.storage_backend != store.backend:
        raise ServiceError(
            ErrorCode.INVALID_CONFIG,
            "Document asset backend does not match the configured asset store.",
            {"asset_backend": asset.storage_backend, "configured_backend": store.backend},
        )
    content = store.get(asset.storage_key)
    return Response(content=content, media_type=asset.mime_type, headers={"X-Document-Asset-Id": asset.asset_id})


@app.get("/assets")
def list_document_assets(
    kb_name: str = "default",
    api_key: ApiKey = Depends(require_scope("admin")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, kb_name)
    manifest = load_asset_manifest(kb_name, settings)
    return {
        "kb_name": kb_name,
        "schema_version": manifest.schema_version,
        "assets": [
            {
                "asset_id": asset.asset_id,
                "doc_id": asset.doc_id,
                "source_file": asset.source_file,
                "type": asset.type,
                "status": asset.status,
                "mime_type": asset.mime_type,
                "page_number": asset.page_number,
                "storage_backend": asset.storage_backend,
                "failure_reason": asset.failure_reason,
            }
            for asset in sorted(manifest.assets.values(), key=lambda row: row.asset_id)
        ],
        "stats": manifest.to_dict()["stats"],
    }


@app.get("/manuals")
def list_manuals(
    kb_name: str = "default",
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.list_manuals(kb_name, api_key, settings, app_state)


@app.post("/manuals/validate")
def validate_manual_metadata(
    request: ManualMetadataValidationRequest,
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.validate_manual_metadata(request, api_key, settings)


@app.post("/manuals/tags/suggest")
def suggest_manual_tags(
    request: ManualTagSuggestRequest,
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.suggest_manual_tags(request, api_key, settings, app_state)


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
    return await api_manual_routes.upload_manual(
        kb_name=kb_name,
        metadata=metadata,
        overwrite=overwrite,
        trigger_rebuild=trigger_rebuild,
        file=file,
        api_key=api_key,
        settings=settings,
        app_state=app_state,
        embedder=embedder,
        get_rebuild_queue=_get_rebuild_queue,
    )


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
    return await api_manual_routes.preview_manual_bulk_import(
        kb_name=kb_name,
        metadata_format=metadata_format,
        metadata=metadata,
        mode=mode,
        overwrite=overwrite,
        metadata_file=metadata_file,
        files=files,
        api_key=api_key,
        settings=settings,
    )


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
    return await api_manual_routes.import_manual_bulk(
        kb_name=kb_name,
        metadata_format=metadata_format,
        metadata=metadata,
        mode=mode,
        overwrite=overwrite,
        selected_rows=selected_rows,
        trigger_rebuild=trigger_rebuild,
        metadata_file=metadata_file,
        files=files,
        api_key=api_key,
        settings=settings,
        app_state=app_state,
        embedder=embedder,
        get_rebuild_queue=_get_rebuild_queue,
    )


@app.patch("/manuals/{manual_id}/metadata")
def patch_manual_metadata(
    manual_id: str,
    request: ManualMetadataUpdateRequest,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.patch_manual_metadata(manual_id, request, api_key, settings)


@app.put("/manuals/{manual_id}/file")
async def put_manual_file(
    manual_id: str,
    kb_name: str = Form("default"),
    file: UploadFile = File(...),
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    return await api_manual_routes.put_manual_file(manual_id, kb_name, file, api_key, settings)


@app.delete("/manuals/{manual_id}")
def remove_manual(
    manual_id: str,
    kb_name: str = "default",
    hard: bool = False,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.remove_manual(manual_id, kb_name, hard, api_key, settings)


@app.get("/manual-library")
def list_manual_library(
    kb_name: str = "default",
    manual_id: str | None = None,
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.list_manual_library(kb_name, manual_id, api_key, settings, app_state)


@app.get("/manual-library/dirty")
def get_manual_library_dirty(
    kb_name: str = "default",
    format: str = "json",
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.manual_library_dirty(kb_name, format, api_key, settings, app_state)


@app.get("/manual-library/diagnostics")
def get_manual_library_diagnostics(
    kb_name: str = "default",
    verify_blobs: bool = False,
    include_jobs: bool = True,
    job_status: str | None = None,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.diagnostics(
        kb_name,
        verify_blobs=verify_blobs,
        include_jobs=include_jobs,
        job_status=job_status,
        api_key=api_key,
        settings=settings,
        app_state=app_state,
        get_rebuild_queue=_get_rebuild_queue,
    )


@app.get("/manual-library/registry/audit")
def get_manual_library_registry_audit(
    kb_name: str = "default",
    manual_id: str | None = None,
    limit: int = 50,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.registry_audit(kb_name, manual_id, limit, api_key, settings)


@app.get("/manual-library/tags")
def get_manual_library_tags(
    kb_name: str = "default",
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.get_tags(kb_name, api_key, settings, app_state)


@app.put("/manual-library/tags/policy")
def put_manual_library_tag_policy(
    request: TagPolicyUpdateRequest,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.put_tag_policy(request, api_key, settings)


@app.post("/manual-library/tags/rewrite/preview")
def preview_manual_library_tag_rewrite(
    request: TagRewriteRequest,
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.preview_tag_rewrite(request, api_key, settings)


@app.post("/manual-library/tags/rewrite")
def commit_manual_library_tag_rewrite(
    request: TagRewriteRequest,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.commit_tag_rewrite_route(request, api_key, settings)


@app.post("/manual-library/rebuild", status_code=202)
def rebuild_manual_library(
    request: ManualLibraryRebuildRequest,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.rebuild_library(request, api_key, settings, app_state, embedder, _get_rebuild_queue)


@app.get("/manual-library/rebuild-jobs")
def list_rebuild_jobs(
    kb_name: str | None = None,
    status: str | None = None,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.list_rebuild_jobs(kb_name, status, api_key, settings, _get_rebuild_queue)


@app.get("/manual-library/rebuild-jobs/{job_id}")
def inspect_rebuild_job(
    job_id: str,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.inspect_rebuild_job(job_id, api_key, settings, _get_rebuild_queue)


@app.post("/manual-library/rebuild-jobs/{job_id}/cancel")
def cancel_rebuild_job(
    job_id: str,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.cancel_rebuild_job(job_id, api_key, settings, _get_rebuild_queue)


@app.post("/manual-library/rebuild-jobs/{job_id}/retry")
def retry_rebuild_job(
    job_id: str,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    return api_manual_routes.retry_rebuild_job(job_id, api_key, settings, _get_rebuild_queue)


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
    return api_admin.clear_cache(request, settings, app_state)


def _resolve_indexgen_target_versions(req: IndexGenBuildShadowRequest) -> dict[str, object]:
    return api_admin.resolve_indexgen_target_versions(req)


@app.post("/admin/generation/build-shadow")
def admin_build_shadow(
    request: IndexGenBuildShadowRequest,
    _api_key: ApiKey = Depends(require_scope("admin")),
):
    return api_admin.build_shadow(request, settings, app_state, embedder)


@app.post("/admin/generation/cancel-shadow")
def admin_cancel_shadow(
    request: IndexGenCancelShadowRequest,
    _api_key: ApiKey = Depends(require_scope("admin")),
):
    return api_admin.cancel_shadow(request, settings, app_state)


@app.post("/admin/generation/swap")
def admin_swap_generation(
    request: IndexGenSwapRequest,
    _api_key: ApiKey = Depends(require_scope("admin")),
):
    return api_admin.swap_generation(request, settings, app_state)


@app.post("/admin/generation/retire")
def admin_retire_generation(
    request: IndexGenRetireRequest,
    _api_key: ApiKey = Depends(require_scope("admin")),
):
    return api_admin.retire_generation(request, settings, app_state)


@app.get("/admin/generation/status")
def admin_generation_status(
    kb_name: str = "default",
    _api_key: ApiKey = Depends(require_scope("admin")),
):
    return api_admin.generation_status(kb_name, settings, app_state)


def _get_rebuild_queue() -> RebuildQueue:
    global rebuild_queue
    if rebuild_queue is None or rebuild_queue.app_state is not app_state or rebuild_queue.cfg is not settings:
        rebuild_queue = RebuildQueue(app_state, settings, embedder=embedder)
    return rebuild_queue
