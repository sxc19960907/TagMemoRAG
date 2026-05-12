from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import sys
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from .anchor import AnchorSystem
from .config import Settings, load_config
from .embedder import create_embedder
from .errors import ErrorCode, KbNotLoadedError, ServiceError
from .logging_setup import configure_logging
from .state import AppState, load_kb
from .storage.json_anchor import JsonAnchorStore
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
        logger.info("model_warmed_up", duration_ms=round((time.perf_counter() - t0) * 1000.0, 3))
    except Exception as exc:
        logger.error("model_warmup_failed", error_type=type(exc).__name__, error_message=str(exc))
        sys.exit(1)
    try:
        loaded = load_kb("default", settings)
        app_state.swap(loaded)
        logger.info(
            "kb_loaded",
            kb_name=loaded.kb_name,
            build_id=loaded.build_id,
            node_count=loaded.graph.number_of_nodes(),
        )
    except KbNotLoadedError:
        logger.warning("kb_load_skipped", kb_name="default")
    logger.info("service_ready", startup_duration_ms=round((time.perf_counter() - startup_t0) * 1000.0, 3))
    try:
        yield
    finally:
        shutdown_t0 = time.perf_counter()
        logger.info("shutdown_started")
        app_state.begin_shutdown()
        drain_t0 = time.perf_counter()
        await asyncio.to_thread(app_state._rebuild_lock.acquire)
        app_state._rebuild_lock.release()
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
        ErrorCode.INTERNAL: 500,
    }.get(code, 500)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
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


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError):
    structlog.get_logger().warning(
        "request_error",
        code=exc.code.value,
        status=_status_for(exc.code),
        exception_type=type(exc).__name__,
    )
    return JSONResponse(status_code=_status_for(exc.code), content=exc.to_dict())


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
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


@app.post("/search")
def search(request: SearchRequest, http_request: Request):
    state = app_state.get_current(request.kb_name)
    t0 = time.perf_counter()
    query_vec = embedder.encode_query(request.question)
    aggregate = request.aggregate or settings.search.aggregate
    if aggregate not in {"max", "sum"}:
        raise ServiceError(
            ErrorCode.INVALID_INPUT,
            "aggregate must be 'max' or 'sum'.",
            {"aggregate": aggregate},
        )
    results = wave_search(
        query_vec,
        state.graph,
        state.vectors,
        state.anchors,
        top_k=request.top_k or settings.search.top_k,
        source_k=request.source_k or settings.search.source_k,
        steps=request.steps if request.steps is not None else settings.search.steps,
        decay=request.decay if request.decay is not None else settings.search.decay,
        amplitude_cutoff=request.amplitude_cutoff
        if request.amplitude_cutoff is not None
        else settings.search.amplitude_cutoff,
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
    )
    return {
        "build_id": state.build_id,
        "kb_name": state.kb_name,
        "trace_id": trace_id,
        "results": [r.to_dict() for r in results],
        "search_time_ms": round(search_time_ms, 3),
    }


@app.post("/rebuild", status_code=202)
def rebuild(request: RebuildRequest):
    task = app_state.start_rebuild(request.docs_dir, request.kb_name, settings, embedder=embedder)
    return task.to_dict()


@app.get("/rebuild/{task_id}")
def get_rebuild(task_id: str):
    task = app_state.rebuild_tasks.get(task_id)
    if not task:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Rebuild task not found.", {"task_id": task_id})
    return task.to_dict()


@app.post("/anchor")
def add_anchor(request: AnchorRequest):
    state = app_state.get_current(request.kb_name)
    store = JsonAnchorStore(f"{settings.storage.data_dir}/{request.kb_name}/anchors.json")
    anchor = AnchorSystem(state, store).add(request.node_id, request.label, request.boost, request.propagation_boost)
    structlog.get_logger().info("anchor_created", anchor_key=anchor.anchor_key, label=anchor.label)
    return anchor.to_dict()


@app.delete("/anchor/{anchor_key}")
def delete_anchor(anchor_key: str, kb_name: str = "default"):
    state = app_state.get_current(kb_name)
    store = JsonAnchorStore(f"{settings.storage.data_dir}/{kb_name}/anchors.json")
    AnchorSystem(state, store).delete(anchor_key)
    structlog.get_logger().info("anchor_deleted", anchor_key=anchor_key)
    return {"status": "deleted", "anchor_key": anchor_key}


@app.get("/anchor")
def list_anchor(kb_name: str = "default"):
    state = app_state.get_current(kb_name)
    return {"anchors": [anchor.to_dict() for anchor in state.anchors.values()]}


@app.get("/graph_info")
def graph_info(kb_name: str = "default"):
    state = app_state.get_current(kb_name)
    return {
        "kb_name": state.kb_name,
        "build_id": state.build_id,
        "node_count": state.graph.number_of_nodes(),
        "edge_count": state.graph.number_of_edges(),
        "meta": state.meta,
        "unresolved_anchors": [anchor.to_dict() for anchor in state.unresolved_anchors],
    }
