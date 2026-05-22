from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import csv
import hashlib
import json
import sys
import time
from io import StringIO
from typing import Literal, cast
import uuid

from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import numpy as np
from pydantic import BaseModel, Field
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from .anchor import AnchorSystem
from .answer import create_answer_generator
from .answer.base import AnswerGenerationError, AnswerGenerator, AnswerRequestContext
from .answer.prompt import build_answer_prompt, validate_generation_citations
from .auth.base import ApiKey
from .auth.config_store import ConfigAuthStore
from .auth.dependencies import ensure_kb_access, rate_limit_dep, require_scope
from .cache.lru_ttl import LRUTTLCache
from .config import Settings, load_config
from .document_assets import create_asset_store, load_asset_manifest
from .embedder import create_embedder
from .errors import ErrorCode, KbNotLoadedError, ServiceError
from .logging_setup import configure_logging
from .manuals import metadata_from_node, public_tags_from_metadata
from .manual_bulk_import import BulkImportMode, BulkUploadedFile, commit_bulk_import, preview_bulk_import
from .manual_library import (
    build_dirty_state_report,
    delete_manual,
    disable_manual,
    library_root,
    list_records,
    load_manifest,
    registry_enabled,
    registry_inspect,
    replace_manual_file,
    update_manual_metadata,
    upsert_manual,
    validate_metadata,
    verify_registry_blobs,
)
from .manual_registry import create_registry
from .metadata_narrowing import NarrowingDecision, infer_metadata_narrowing, merge_inferred_filters
from .observability.metrics import configure_metrics, get_metrics, metrics_response_bytes
from .observability.tracing import configure_tracing, set_span_attributes, start_span
from .rate_limit.memory_sliding import InMemorySlidingWindowStore
from .rebuild_queue import RebuildQueue
from .retrieval import DEFAULT_TOKEN_BUDGET, VisualEvidenceResolver, build_retrieve_response, retrieve_inspect_payload
from .retrieval import VisualRetrievalResolver
from .retrieval_feedback import (
    create_feedback,
    export_eval_promotion,
    list_feedback,
    preview_eval_promotion,
    review_feedback,
)
from .search_runtime import (
    execute_search,
    search_ann_enabled,
    search_cache_suffix,
    search_debug_enabled,
    search_debug_payload,
)
from .wave_tag_spike import GhostTag
from .state import AppState, load_kb, start_library_rebuild
from .storage.json_anchor import JsonAnchorStore
from .tag_suggestions import DEFAULT_LIMIT, suggest_tags
from .visual_retrieval import create_visual_components
from .tag_governance import (
    commit_tag_rewrite,
    load_tag_policy,
    resolve_tags_for_search,
    save_tag_policy,
    tag_usage_report,
    preview_tag_rewrite,
)
from .types import GraphState
from .wave_searcher import normalize_filters

settings = load_config()
app_state = AppState()
embedder = None  # lazily created in lifespan to avoid import-time model download
rebuild_queue: RebuildQueue | None = None
WEB_DIR = Path(__file__).resolve().parent / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


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


class GhostTagSpec(BaseModel):
    """Caller-supplied tag with explicit vector, bypassing the KB tag store.

    `vector` length must equal the model embedding dim at request time;
    mismatched ghosts are silently skipped and counted in `info.ghost_skipped_dim_mismatch`.
    """

    name: str = Field(..., min_length=1, max_length=128)
    vector: list[float] = Field(..., min_length=1)
    is_core: bool = False


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
    debug: bool | None = None
    # Phase 2b-2: caller-supplied "spotlight" tags. Only take effect under
    # `wave_phase1.dynamic_boost_factor_strategy="pyramid"` (PRD R10);
    # otherwise they round-trip through `info.core_tags_input/resolved` for
    # diagnostics with no impact on weights.
    core_tags: list[str] = Field(default_factory=list)
    ghost_tags: list[GhostTagSpec] = Field(default_factory=list)
    # T2: optional per-request budget override; missing fields fall through to
    # Settings.queryplan.default_*. None means "use settings defaults entirely".
    budget: "BudgetSpec | None" = None
    mode: Literal["classic", "agentic"] | None = None
    agentic: "AgenticRequestOverrides | None" = None


class AgenticRequestOverrides(BaseModel):
    decision_enabled: bool | None = None
    max_iterations: int | None = Field(default=None, ge=0)
    max_agent_tokens: int | None = Field(default=None, ge=1)
    max_tool_calls: int | None = Field(default=None, ge=0)


class BudgetSpec(BaseModel):
    """T2: optional per-request resource budget override.

    Missing fields fall through to Settings.queryplan.default_*. The
    deadline_at lifecycle field on the runtime Budget is computed by
    build_plan and never appears in the API surface.
    """

    latency_ms: int | None = Field(default=None, ge=1)
    rerank_tier: Literal["off", "tier1", "tier2"] | None = None
    max_evidence: int | None = Field(default=None, ge=1)
    allow_external_reranker: bool | None = None

    def to_planner_dict(self) -> dict:
        """Convert to the dict shape expected by build_plan(budget_spec=...)."""
        out: dict = {}
        if self.latency_ms is not None:
            out["latency_ms"] = self.latency_ms
        if self.rerank_tier is not None:
            out["rerank_tier"] = self.rerank_tier
        if self.max_evidence is not None:
            out["max_evidence"] = self.max_evidence
        if self.allow_external_reranker is not None:
            out["allow_external_reranker"] = self.allow_external_reranker
        return out


class RetrieveRequest(SearchRequest):
    token_budget: int = Field(default=DEFAULT_TOKEN_BUDGET, ge=0, le=128000)


class AnswerRequest(RetrieveRequest):
    answer_token_budget: int | None = Field(default=None, ge=1, le=128000)
    include_retrieve: bool = True


class QaAnswerRequest(BaseModel):
    question: str
    include_retrieve: bool = True


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
    mode: str = "full"
    allow_fallback: bool = True


class TagPolicyUpdateRequest(BaseModel):
    kb_name: str = "default"
    policy: dict[str, object]


class TagRewriteRequest(BaseModel):
    kb_name: str = "default"
    source_tags: list[str]
    target_tag: str
    mode: str = "merge"
    update_policy: bool = False
    policy_alias_mode: str | None = None


class AnchorRequest(BaseModel):
    node_id: int
    label: str
    boost: float = Field(default=2.0, gt=0)
    propagation_boost: float = Field(default=1.0, gt=0)
    kb_name: str = "default"


class CacheClearRequest(BaseModel):
    kb_name: str | None = None


class IndexGenBuildShadowRequest(BaseModel):
    kb_name: str = "default"
    docs_dir: str | None = None
    embedding_model_id: str | None = None
    embedding_model_version: str | None = None
    parser_version: str | None = None
    chunker_version: str | None = None
    index_schema_version: int | None = None


class IndexGenCancelShadowRequest(BaseModel):
    kb_name: str = "default"


class IndexGenSwapRequest(BaseModel):
    kb_name: str = "default"


class IndexGenRetireRequest(BaseModel):
    kb_name: str = "default"
    generation: int
    force: bool = False


class FeedbackSubmitRequest(BaseModel):
    kb_name: str = "default"
    trace_id: str = ""
    search_id: str = ""
    retrieve_id: str = ""
    build_id: str = ""
    query: str = Field(..., max_length=1000)
    outcome: str
    selected_results: list[dict[str, object]] = Field(default_factory=list, max_length=20)
    selected_evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    selected_context_item_ids: list[str] = Field(default_factory=list, max_length=20)
    answerable: bool | None = None
    failure_reason: str = Field(default="", max_length=120)
    expected: list[dict[str, object]] = Field(default_factory=list, max_length=20)
    note: str = Field(default="", max_length=2000)
    plan_id: str | None = Field(default=None, max_length=120)


class FeedbackReviewRequest(BaseModel):
    kb_name: str = "default"
    status: str | None = None
    operator_note: str | None = Field(default=None, max_length=2000)


class FeedbackPromoteRequest(BaseModel):
    kb_name: str = "default"
    feedback_ids: list[str]
    output_path: str | None = None
    append: bool = False
    overwrite: bool = False


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


def _spotlight_cache_suffix(request: SearchRequest) -> str:
    """Stable hash of caller-supplied core_tags / ghost_tags for cache keying.

    Different spotlight inputs ⇒ different results, so cache must split on them.
    Empty lists ⇒ stable empty suffix (no cache busting for default callers).
    """
    if not request.core_tags and not request.ghost_tags:
        return "spot:none"
    payload = {
        "core": [str(t).strip().lower() for t in request.core_tags],
        "ghost": [
            {
                "name": str(g.name).strip().lower(),
                "is_core": bool(g.is_core),
                "vec_hash": hashlib.sha256(
                    np.asarray(g.vector, dtype=np.float32).tobytes()
                ).hexdigest()[:16],
            }
            for g in request.ghost_tags
        ],
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"spot:{digest}"


def _compute_cache_key(request: SearchRequest, state: GraphState) -> str:
    params = _search_param_values(request)
    filter_dict, _narrowing = _resolved_filter_dict(request, state)
    canonical_filters = normalize_filters(filter_dict)
    strategy_suffix = search_cache_suffix(settings, has_filters=bool(canonical_filters))
    debug_suffix = f"debug:{int(search_debug_enabled(request.debug, settings))}"
    spotlight_suffix = _spotlight_cache_suffix(request)
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
        strategy_suffix,
        debug_suffix,
        spotlight_suffix,
    ]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _compute_search_id(request: SearchRequest, state: GraphState, trace_id: str) -> str:
    params = _search_param_values(request)
    filter_dict, _narrowing = _resolved_filter_dict(request, state)
    canonical_filters = normalize_filters(filter_dict)
    strategy_suffix = search_cache_suffix(settings, has_filters=bool(canonical_filters))
    debug_suffix = f"debug:{int(search_debug_enabled(request.debug, settings))}"
    spotlight_suffix = _spotlight_cache_suffix(request)
    parts = [
        state.kb_name,
        state.build_id,
        trace_id,
        _normalize_question(request.question),
        str(params["top_k"]),
        str(params["source_k"]),
        str(params["steps"]),
        str(params["decay"]),
        str(params["amplitude_cutoff"]),
        str(params["aggregate"]),
        json.dumps(canonical_filters, sort_keys=True, separators=(",", ":")),
        strategy_suffix,
        debug_suffix,
        spotlight_suffix,
    ]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _compute_retrieve_id(request: RetrieveRequest, state: GraphState, trace_id: str) -> str:
    base = _compute_search_id(request, state, trace_id)
    parts = ["retrieve", base, str(int(request.token_budget))]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _build_and_log_plan(request: SearchRequest, state: GraphState):
    """T2: construct QueryPlan + insert basic row. Returns (plan, plan_log).

    Caller is responsible for calling plan_log.update_result_async() before
    returning the response to fill in result columns.
    """
    from .queryplan import PlanLog, build_plan
    from .agentic.surface import resolve_agentic_mode, stamp_plan_mode

    filter_dict, _narrowing = _resolved_filter_dict(request, state)
    budget_spec = request.budget.to_planner_dict() if request.budget else None
    if request.agentic is not None:
        budget_spec = dict(budget_spec or {})
        if request.agentic.max_iterations is not None:
            budget_spec["max_iterations"] = request.agentic.max_iterations
        if request.agentic.max_agent_tokens is not None:
            budget_spec["max_agent_tokens"] = request.agentic.max_agent_tokens
        if request.agentic.max_tool_calls is not None:
            budget_spec["max_tool_calls"] = request.agentic.max_tool_calls
    plan = build_plan(
        request.question,
        request.kb_name,
        settings,
        filters=filter_dict,
        budget_spec=budget_spec,
    )
    resolution = resolve_agentic_mode(
        settings_mode=settings.agentic.mode,
        request_mode=request.mode,
    )
    plan = stamp_plan_mode(plan, resolution)
    plan_log = PlanLog(request.kb_name, settings)
    plan_log.insert_basic(plan)
    return plan, plan_log


def _served_by_generation(state: GraphState) -> int | None:
    """T2: Try to read served_by_generation from state.meta; falls back to None
    when index.json is not yet wired into rebuilds."""
    if not isinstance(state.meta, dict):
        return None
    gen = state.meta.get("served_by_generation")
    return int(gen) if gen is not None else None


_RERANK_DISPATCHER_CACHE: dict[int, "object"] = {}


def _rerank_dispatcher():
    """T3: lazy singleton dispatcher keyed by current Settings identity.

    Rebuilt when api.settings is replaced (test fixtures swap settings
    between tests).
    """
    from .reranker import RerankerDispatcher

    key = id(settings)
    cached = _RERANK_DISPATCHER_CACHE.get(key)
    if cached is None:
        cached = RerankerDispatcher(settings)
        _RERANK_DISPATCHER_CACHE[key] = cached
    return cached


def _reorder_results(original_results, rerank_outcome):
    """Reorder execute_search results by rerank_outcome's chunk_id ordering.

    Items not in rerank_outcome are dropped (rerank already filtered to top_n).
    Falls back to original order when rerank_outcome is empty.
    """
    if not rerank_outcome.items:
        return list(original_results)
    from .reranker.dispatcher import _candidate_chunk_id

    by_id = {_candidate_chunk_id(r): r for r in original_results}
    out = []
    for item in rerank_outcome.items:
        cid = item.chunk_id
        if cid in by_id and by_id[cid] is not None:
            out.append(by_id[cid])
    return out


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
    route = _route_qa_question(request.question, api_key)
    if route["kind"] == "not_ready":
        return _qa_not_ready_response(route)
    if route["kind"] == "clarification":
        return _qa_clarification_response(request, route)

    kb_name = str(route["kb_name"])
    answer_request = AnswerRequest(
        question=request.question,
        kb_name=kb_name,
        top_k=5,
        source_k=8,
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
            "tagmemorag.query_len": len(request.question),
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


def _route_qa_question(question: str, api_key: ApiKey) -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    for kb_name in app_state.list_kbs():
        if not api_key.allows_kb(kb_name):
            continue
        try:
            state = app_state.get_kb(kb_name)
        except KbNotLoadedError:
            continue
        candidates.append({
            "kb_name": kb_name,
            "label": _qa_kb_label(state),
            "score": _qa_route_score(question, state),
        })

    if not candidates:
        return {"kind": "not_ready", "candidates": []}
    if len(candidates) == 1:
        return {"kind": "answered", "kb_name": candidates[0]["kb_name"], "reason": "single_kb"}

    ranked = sorted(candidates, key=lambda item: (-float(item["score"]), str(item["kb_name"])))
    best = ranked[0]
    second_score = float(ranked[1]["score"])
    if float(best["score"]) >= 2 and float(best["score"]) >= second_score + 1:
        return {"kind": "answered", "kb_name": best["kb_name"], "reason": "lexical_route"}
    return {"kind": "clarification", "candidates": [_qa_public_candidate(item) for item in ranked[:5]]}


def _qa_not_ready_response(route: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "qa_answer.v1",
        "route": {"kind": "not_ready", "candidates": route.get("candidates", [])},
        "answer": {
            "kind": "error",
            "text": "The manual assistant is not ready yet. Please import manuals and rebuild the knowledge base before asking questions.",
            "confidence": 0.0,
            "citations": [],
            "refusal_reason": "kb_not_ready",
            "missing_evidence_hints": ["kb_not_ready"],
            "model_id": None,
            "model_version": None,
            "prompt_version": None,
            "warnings": [],
        },
        "warnings": ["qa_route:not_ready"],
    }


def _qa_clarification_response(request: QaAnswerRequest, route: dict[str, object]) -> dict[str, object]:
    candidates = route.get("candidates", [])
    return {
        "schema_version": "qa_answer.v1",
        "route": {"kind": "clarification", "candidates": candidates},
        "answer": {
            "kind": "clarification",
            "text": "Which product or manual is this question about?",
            "confidence": 0.0,
            "citations": [],
            "refusal_reason": "needs_clarification",
            "missing_evidence_hints": ["choose_product_or_manual"],
            "model_id": None,
            "model_version": None,
            "prompt_version": None,
            "warnings": [],
        },
        "warnings": ["qa_route:needs_clarification"],
        "question": request.question,
    }


def _qa_public_candidate(candidate: dict[str, object]) -> dict[str, object]:
    return {
        "kb_name": candidate["kb_name"],
        "label": candidate["label"],
    }


def _qa_kb_label(state: GraphState) -> str:
    labels: list[str] = []
    for _, data in list(state.graph.nodes(data=True))[:50]:
        metadata = data.get("metadata") or {}
        for key in ("manual_title", "title", "product_model", "product_category", "brand"):
            value = metadata.get(key) or data.get(key)
            if value:
                labels.append(str(value))
    return labels[0] if labels else state.kb_name


def _qa_route_score(question: str, state: GraphState) -> int:
    query = question.casefold()
    score = 0
    if state.kb_name.casefold() in query:
        score += 3
    seen: set[str] = set()
    for _, data in list(state.graph.nodes(data=True))[:80]:
        metadata = data.get("metadata") or {}
        values = [
            data.get("header"),
            data.get("path"),
            data.get("source_file"),
            metadata.get("manual_title"),
            metadata.get("title"),
            metadata.get("brand"),
            metadata.get("product_category"),
            metadata.get("product_model"),
            metadata.get("manual_id"),
        ]
        for value in values:
            if not value:
                continue
            text = str(value).casefold()
            if text in seen:
                continue
            seen.add(text)
            if len(text) >= 2 and text in query:
                score += 2
    return score


def _search_impl(request: SearchRequest, http_request: Request, state: GraphState, t0: float):
    plan, plan_log = _build_and_log_plan(request, state)
    warnings: list[str] = []

    # Out-of-scope short-circuit (T2 D2): skip retrieval, return empty results,
    # still write plan log so we can study these queries later.
    from .queryplan import Intent

    if plan.intent == Intent.OUT_OF_SCOPE:
        warnings.append("out_of_scope_intent")
        trace_id = str(getattr(http_request.state, "trace_id", ""))
        search_id = _compute_search_id(request, state, trace_id)
        payload = {
            "build_id": state.build_id,
            "kb_name": state.kb_name,
            "trace_id": trace_id,
            "search_id": search_id,
            "plan_id": plan.plan_id,
            "results": [],
            "search_time_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            "cache": "disabled",
            "warnings": list(warnings),
        }
        plan_log.update_result_async(plan.plan_id, {
            "served_by_generation": _served_by_generation(state),
            "served_by_build_id": state.build_id,
            "cache_status": "disabled",
            "evidence_ids": [],
            "latency_ms_observed": int((time.perf_counter() - t0) * 1000.0),
            "warnings": list(warnings),
        })
        get_metrics().record_search(
            kb_name=state.kb_name,
            cache_status="disabled",
            outcome="success",
            duration=time.perf_counter() - t0,
            result_count=0,
        )
        return payload

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
        search_id = _compute_search_id(request, state, trace_id)
        payload = {**cached, "trace_id": trace_id, "search_id": search_id, "search_time_ms": round(search_time_ms, 3), "cache": "hit", "plan_id": plan.plan_id}
        result_count = len(payload.get("results", []))
        plan_log.update_result_async(plan.plan_id, {
            "served_by_generation": _served_by_generation(state),
            "served_by_build_id": state.build_id,
            "cache_status": "hit",
            "evidence_ids": [],
            "latency_ms_observed": int(search_time_ms),
            "warnings": list(warnings),
        })
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
        filter_dict, narrowing = _resolved_filter_dict(request, state)
        ghost_tag_args = tuple(
            GhostTag(
                name=str(g.name),
                vector=np.asarray(g.vector, dtype=np.float32),
                is_core=bool(g.is_core),
            )
            for g in request.ghost_tags
        )
        execution = execute_search(
            state=state,
            query_vec=query_vec,
            settings=settings,
            query_text=request.question,
            top_k=int(params["top_k"]),
            source_k=int(params["source_k"]),
            steps=int(params["steps"]),
            decay=float(params["decay"]),
            amplitude_cutoff=float(params["amplitude_cutoff"]),
            aggregate=aggregate,
            filters=filter_dict,
            boost_filters=narrowing.boost_filters,
            core_tags=tuple(request.core_tags),
            ghost_tags=ghost_tag_args,
        )
        results = execution.results
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
        search_strategy=execution.strategy,
        ann_candidate_count=execution.ann_candidate_count,
        ann_fallback_reason=execution.ann_fallback_reason,
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
            "tagmemorag.search.strategy": execution.strategy,
            "tagmemorag.search.ann_candidate_count": execution.ann_candidate_count,
            "tagmemorag.search.ann_fallback_reason": execution.ann_fallback_reason,
        }
    )
    payload = {
        "build_id": state.build_id,
        "kb_name": state.kb_name,
        "trace_id": trace_id,
        "search_id": _compute_search_id(request, state, trace_id),
        "plan_id": plan.plan_id,
        "results": [r.to_dict() for r in results],
        "search_time_ms": round(search_time_ms, 3),
        "cache": "miss",
    }
    if warnings:
        payload["warnings"] = list(warnings)
    if search_debug_enabled(request.debug, settings):
        payload["debug"] = search_debug_payload(
            execution,
            params,
            ann_enabled=search_ann_enabled(state, settings),
        )
        payload["debug"]["metadata_narrowing"] = narrowing.to_debug_dict(
            enabled=settings.search.metadata_narrowing_enabled
        )
    if cache is not None:
        cache.set(
            cache_key,
            {k: v for k, v in payload.items() if k not in {"trace_id", "search_id", "search_time_ms", "cache", "plan_id"}},
            kb_name=request.kb_name,
        )
        get_metrics().record_cache_operation(operation="set", outcome="success")
        get_metrics().set_cache_entries(len(cache))
    plan_log.update_result_async(plan.plan_id, {
        "served_by_generation": _served_by_generation(state),
        "served_by_build_id": state.build_id,
        "cache_status": cache_status,
        "evidence_ids": [r.id for r in results if hasattr(r, "id")],
        "latency_ms_observed": int(search_time_ms),
        "warnings": list(warnings),
    })
    return payload


def _build_answer_response(request: AnswerRequest, retrieve_payload: dict) -> dict:
    warnings = list(retrieve_payload.get("warnings") or [])
    answerability = dict(retrieve_payload.get("answerability") or {})
    if not bool(answerability.get("answerable")):
        reason = str(answerability.get("fallback_reason") or "insufficient_evidence")
        answer_obj = _answer_error_obj(
            kind="refusal",
            reason=reason,
            warning=f"answer_refused:{reason}",
            confidence=float(answerability.get("confidence") or 0.0),
            missing_evidence_hints=[reason],
        )
        warnings.append(f"answer_refused:{reason}")
        return _answer_response_payload(request, retrieve_payload, answer_obj, warnings)

    if not settings.answer.enabled:
        answer_obj = _answer_error_obj(
            kind="error",
            reason="generation_disabled",
            warning="answer_generation_disabled",
            confidence=float(answerability.get("confidence") or 0.0),
            missing_evidence_hints=[],
        )
        warnings.append("answer_generation_disabled")
        return _answer_response_payload(request, retrieve_payload, answer_obj, warnings)

    prompt = build_answer_prompt(
        question=request.question,
        retrieve_payload=retrieve_payload,
        prompt_version=settings.answer.prompt_version,
    )
    context = AnswerRequestContext(
        question=request.question,
        retrieve_payload=retrieve_payload,
        prompt=prompt,
        max_output_tokens=int(request.answer_token_budget or settings.answer.max_output_tokens),
    )
    try:
        generation = _answer_generator().generate(context)
        cleaned = validate_generation_citations(generation, prompt.allowed_citation_ids)
        answer_obj = cleaned.to_answer_dict(confidence=float(answerability.get("confidence") or 0.0))
        warnings.extend(cleaned.warnings)
    except (AnswerGenerationError, ServiceError, ValueError) as exc:
        reason = type(exc).__name__
        answer_obj = _answer_error_obj(
            kind="error",
            reason="generation_failed",
            warning=f"answer_generation_failed:{reason}",
            confidence=float(answerability.get("confidence") or 0.0),
            missing_evidence_hints=[],
        )
        warnings.append(f"answer_generation_failed:{reason}")
    return _answer_response_payload(request, retrieve_payload, answer_obj, warnings)


def _answer_error_obj(
    *,
    kind: str,
    reason: str,
    warning: str,
    confidence: float,
    missing_evidence_hints: list[str],
) -> dict:
    return {
        "kind": kind,
        "text": "",
        "confidence": confidence,
        "citations": [],
        "refusal_reason": reason,
        "missing_evidence_hints": missing_evidence_hints,
        "model_id": settings.answer.model_id or settings.answer.provider,
        "model_version": settings.answer.model_version,
        "prompt_version": settings.answer.prompt_version,
        "warnings": [warning],
    }


def _answer_response_payload(request: AnswerRequest, retrieve_payload: dict, answer_obj: dict, warnings: list[str]) -> dict:
    payload = {
        "schema_version": "answer.v1",
        "build_id": retrieve_payload.get("build_id", ""),
        "kb_name": retrieve_payload.get("kb_name", request.kb_name),
        "trace_id": retrieve_payload.get("trace_id", ""),
        "plan_id": retrieve_payload.get("plan_id", ""),
        "answer": answer_obj,
        "warnings": list(dict.fromkeys(warnings)),
    }
    if request.include_retrieve:
        payload["retrieve"] = retrieve_payload
    return payload


_ANSWER_GENERATOR_CACHE: dict[int, AnswerGenerator] = {}


def _answer_generator() -> AnswerGenerator:
    key = id(settings)
    cached = _ANSWER_GENERATOR_CACHE.get(key)
    if cached is None:
        cached = create_answer_generator(settings)
        _ANSWER_GENERATOR_CACHE[key] = cached
    return cached


def _retrieve_impl(request: RetrieveRequest, http_request: Request, state: GraphState, t0: float):
    plan, plan_log = _build_and_log_plan(request, state)
    warnings: list[str] = []

    # Out-of-scope short-circuit (T2 D2)
    from .queryplan import Intent
    from .queryplan.budget import BudgetGuard

    if plan.intent == Intent.OUT_OF_SCOPE:
        warnings.append("out_of_scope_intent")
        trace_id = str(getattr(http_request.state, "trace_id", ""))
        search_id = _compute_search_id(request, state, trace_id)
        retrieve_id = _compute_retrieve_id(request, state, trace_id)
        empty_payload = {
            "build_id": state.build_id,
            "kb_name": state.kb_name,
            "trace_id": trace_id,
            "search_id": search_id,
            "retrieve_id": retrieve_id,
            "plan_id": plan.plan_id,
            "results": [],
            "evidence": [],
            "context_pack": {"items": []},
            "search_time_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            "warnings": list(warnings),
        }
        plan_log.update_result_async(plan.plan_id, {
            "served_by_generation": _served_by_generation(state),
            "served_by_build_id": state.build_id,
            "cache_status": "disabled",
            "evidence_ids": [],
            "latency_ms_observed": int((time.perf_counter() - t0) * 1000.0),
            "warnings": list(warnings),
        })
        get_metrics().record_search(
            kb_name=state.kb_name,
            cache_status="disabled",
            outcome="success",
            duration=time.perf_counter() - t0,
            result_count=0,
        )
        return empty_payload

    emb_t0 = time.perf_counter()
    try:
        with start_span("tagmemorag.retrieve.embedding", **{"tagmemorag.kb_name": state.kb_name}):
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
    with start_span("tagmemorag.retrieve.wave", **{"tagmemorag.kb_name": state.kb_name}):
        filter_dict, narrowing = _resolved_filter_dict(request, state)
        ghost_tag_args = tuple(
            GhostTag(
                name=str(g.name),
                vector=np.asarray(g.vector, dtype=np.float32),
                is_core=bool(g.is_core),
            )
            for g in request.ghost_tags
        )
        # T3 D1: when reranker active, expand candidate window to
        # rerank_candidates_n; reranker prunes back to top_n; downstream
        # build_retrieve_response truncates to user's token_budget.
        effective_top_k = int(params["top_k"])
        rerank_active = (
            plan.budget.rerank_tier != "off"
            and plan.budget.rerank_candidates_n > 0
        )
        if rerank_active:
            effective_top_k = max(effective_top_k, plan.budget.rerank_candidates_n)
        execution = execute_search(
            state=state,
            query_vec=query_vec,
            settings=settings,
            query_text=request.question,
            top_k=effective_top_k,
            source_k=int(params["source_k"]),
            steps=int(params["steps"]),
            decay=float(params["decay"]),
            amplitude_cutoff=float(params["amplitude_cutoff"]),
            aggregate=aggregate,
            filters=filter_dict,
            boost_filters=narrowing.boost_filters,
            core_tags=tuple(request.core_tags),
            ghost_tags=ghost_tag_args,
        )
    candidates_used = execution.results
    rerank_log_entry: dict | None = None
    if rerank_active:
        guard = BudgetGuard(plan)
        rerank_outcome = _rerank_dispatcher().rerank(
            plan,
            list(execution.results),
            guard,
            query_text=request.question,
        )
        if rerank_outcome.warnings:
            warnings.extend(rerank_outcome.warnings)
        candidates_used = _reorder_results(execution.results, rerank_outcome)
        rerank_log_entry = {
            "vendor_used": rerank_outcome.vendor_used,
            "calibrator": settings.reranker.calibrator,
            "calibrated": True,
            "latency_ms": rerank_outcome.latency_ms,
            "top_n_returned": len(rerank_outcome.items),
            "truncated_count": len(rerank_outcome.truncated_chunk_ids),
            "cache_status": rerank_outcome.cache_status,
            "warnings": list(rerank_outcome.warnings),
        }
    search_time_ms = (time.perf_counter() - t0) * 1000.0
    trace_id = str(getattr(http_request.state, "trace_id", ""))
    search_id = _compute_search_id(request, state, trace_id)
    asset_manifest = load_asset_manifest(state.kb_name, settings) if settings.assets.enabled else None
    visual_provider, visual_reranker = create_visual_components(settings)
    payload = build_retrieve_response(
        results=candidates_used,
        build_id=state.build_id,
        kb_name=state.kb_name,
        trace_id=trace_id,
        search_id=search_id,
        retrieve_id=_compute_retrieve_id(request, state, trace_id),
        token_budget=request.token_budget,
        search_time_ms=search_time_ms,
        visual_resolver=VisualEvidenceResolver(kb_name=state.kb_name, manifest=asset_manifest) if settings.assets.enabled else None,
        visual_retrieval_resolver=VisualRetrievalResolver(
            kb_name=state.kb_name,
            manifest=asset_manifest,
            provider=visual_provider,
            reranker=visual_reranker,
            enabled=settings.visual_retrieval.enabled,
            max_candidates=settings.visual_retrieval.max_candidates,
            min_score=settings.visual_retrieval.min_score,
            trigger=settings.visual_retrieval.trigger,
        ),
        query_text=request.question,
    )
    if search_debug_enabled(request.debug, settings):
        payload["debug"] = search_debug_payload(
            execution,
            params,
            ann_enabled=search_ann_enabled(state, settings),
        )
        payload["debug"]["metadata_narrowing"] = narrowing.to_debug_dict(
            enabled=settings.search.metadata_narrowing_enabled
        )
        payload["debug"]["retrieve_inspect"] = retrieve_inspect_payload(payload)
    get_metrics().record_search(
        kb_name=state.kb_name,
        cache_status="disabled",
        outcome="success",
        duration=time.perf_counter() - t0,
        result_count=len(execution.results),
    )
    set_span_attributes(
        **{
            "tagmemorag.result_count": len(execution.results),
            "tagmemorag.search.strategy": execution.strategy,
        }
    )
    structlog.get_logger().info(
        "retrieve",
        kb_name=state.kb_name,
        build_id=state.build_id,
        query_len=len(request.question),
        top_k=request.top_k or settings.search.top_k,
        result_count=len(execution.results),
        latency_ms=round(search_time_ms, 3),
        search_strategy=execution.strategy,
    )
    payload["plan_id"] = plan.plan_id
    if warnings:
        payload["warnings"] = list(warnings)
    plan_log.update_result_async(plan.plan_id, {
        "served_by_generation": _served_by_generation(state),
        "served_by_build_id": state.build_id,
        "cache_status": "disabled",
        "evidence_ids": [
            ev.get("evidence_id") for ev in payload.get("evidence", [])
            if isinstance(ev, dict) and ev.get("evidence_id")
        ],
        "latency_ms_observed": int(search_time_ms),
        "warnings": list(warnings),
        "rerank": rerank_log_entry,
    })
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


@app.post("/search/feedback")
def submit_search_feedback(
    request: FeedbackSubmitRequest,
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, request.kb_name)
    feedback = create_feedback(request.kb_name, request.model_dump(), settings)
    structlog.get_logger().info(
        "search_feedback_created",
        kb_name=feedback.kb_name,
        outcome=feedback.outcome,
        status=feedback.status,
        trace_id=feedback.trace_id,
    )
    return {"feedback": feedback.to_dict()}


@app.post("/retrieve/feedback")
def submit_retrieve_feedback(
    request: FeedbackSubmitRequest,
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, request.kb_name)
    feedback = create_feedback(request.kb_name, request.model_dump(), settings)
    structlog.get_logger().info(
        "retrieve_feedback_created",
        kb_name=feedback.kb_name,
        outcome=feedback.outcome,
        status=feedback.status,
        trace_id=feedback.trace_id,
    )
    return {"feedback": feedback.to_dict()}


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
    ensure_kb_access(api_key, kb_name)
    rows = list_feedback(kb_name, settings, status=status, outcome=outcome, query=query, limit=limit)
    return {"kb_name": kb_name, "feedback": [row.to_dict() for row in rows]}


@app.patch("/search/feedback/{feedback_id}")
def patch_search_feedback(
    feedback_id: str,
    request: FeedbackReviewRequest,
    api_key: ApiKey = Depends(require_scope("admin")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, request.kb_name)
    feedback = review_feedback(
        request.kb_name,
        feedback_id,
        settings,
        status=request.status,
        operator_note=request.operator_note,
    )
    structlog.get_logger().info(
        "search_feedback_reviewed",
        kb_name=feedback.kb_name,
        status=feedback.status,
        outcome=feedback.outcome,
        trace_id=feedback.trace_id,
    )
    return {"feedback": feedback.to_dict()}


@app.post("/search/feedback/promote/preview")
def preview_search_feedback_promotion(
    request: FeedbackPromoteRequest,
    api_key: ApiKey = Depends(require_scope("admin")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, request.kb_name)
    preview = preview_eval_promotion(
        request.kb_name,
        request.feedback_ids,
        settings,
        output_path=request.output_path,
    )
    return preview.to_dict()


@app.post("/search/feedback/promote")
def promote_search_feedback(
    request: FeedbackPromoteRequest,
    api_key: ApiKey = Depends(require_scope("admin")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, request.kb_name)
    preview = export_eval_promotion(
        request.kb_name,
        request.feedback_ids,
        settings,
        output_path=request.output_path,
        append=request.append,
        overwrite=request.overwrite,
    )
    structlog.get_logger().info(
        "search_feedback_promoted",
        kb_name=request.kb_name,
        status="promoted",
        count=len(preview.cases),
    )
    return preview.to_dict()


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
        tag_policy=load_tag_policy(request.kb_name, settings),
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
    rebuild_payload = _request_library_rebuild(kb_name, mode="auto", allow_fallback=True, trigger="upload") if trigger_rebuild else {}
    structlog.get_logger().info("manual_library_mutation", kb_name=kb_name, manual_id=record.manual_id, action="upsert", status=record.status)
    return {"record": record.to_dict(), "rebuild_required": True, **rebuild_payload}


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
    rebuild_payload = _request_library_rebuild(kb_name, mode="auto", allow_fallback=True, trigger="bulk_import") if trigger_rebuild and result.imported_count else {}
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


@app.get("/manual-library/dirty")
def get_manual_library_dirty(
    kb_name: str = "default",
    format: str = "json",
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
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


@app.get("/manual-library/diagnostics")
def get_manual_library_diagnostics(
    kb_name: str = "default",
    verify_blobs: bool = False,
    include_jobs: bool = True,
    job_status: str | None = None,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, kb_name)
    return _manual_library_diagnostics(
        kb_name,
        verify_blobs=verify_blobs,
        include_jobs=include_jobs,
        job_status=job_status,
        api_key=api_key,
    )


@app.get("/manual-library/registry/audit")
def get_manual_library_registry_audit(
    kb_name: str = "default",
    manual_id: str | None = None,
    limit: int = 50,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
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
                "detail": _safe_audit_detail(event.detail),
            }
            for event in newest_first
        ],
    }


@app.get("/manual-library/tags")
def get_manual_library_tags(
    kb_name: str = "default",
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, kb_name)
    graph_state = app_state.kbs.get(kb_name)
    return tag_usage_report(kb_name, settings, graph_state=graph_state)


@app.put("/manual-library/tags/policy")
def put_manual_library_tag_policy(
    request: TagPolicyUpdateRequest,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
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


@app.post("/manual-library/tags/rewrite/preview")
def preview_manual_library_tag_rewrite(
    request: TagRewriteRequest,
    api_key: ApiKey = Depends(require_scope("search")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, request.kb_name)
    mode = _parse_rewrite_mode(request.mode)
    preview = preview_tag_rewrite(
        request.kb_name,
        settings,
        source_tags=request.source_tags,
        target_tag=request.target_tag,
        mode=mode,
    )
    return preview.to_dict()


@app.post("/manual-library/tags/rewrite")
def commit_manual_library_tag_rewrite(
    request: TagRewriteRequest,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, request.kb_name)
    mode = _parse_rewrite_mode(request.mode)
    alias_mode = _parse_alias_mode(request.policy_alias_mode)
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


@app.post("/manual-library/rebuild", status_code=202)
def rebuild_manual_library(
    request: ManualLibraryRebuildRequest,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    ensure_kb_access(api_key, request.kb_name)
    if request.mode not in {"full", "incremental", "auto"}:
        raise ServiceError(ErrorCode.INVALID_INPUT, "rebuild mode must be full, incremental, or auto.", {"mode": request.mode})
    return _request_library_rebuild(
        request.kb_name,
        mode=request.mode,
        allow_fallback=request.allow_fallback,
        trigger="api",
        top_level=True,
    )


@app.get("/manual-library/rebuild-jobs")
def list_rebuild_jobs(
    kb_name: str | None = None,
    status: str | None = None,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    if kb_name is not None:
        ensure_kb_access(api_key, kb_name)
    queue = _require_rebuild_queue()
    jobs = [
        job
        for job in queue.list_jobs(kb_name=kb_name, status=status)
        if api_key.allows_kb(str(job.get("kb_name") or ""))
    ]
    return {"jobs": jobs}


@app.get("/manual-library/rebuild-jobs/{job_id}")
def inspect_rebuild_job(
    job_id: str,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    queue = _require_rebuild_queue()
    job = queue.inspect(job_id)
    ensure_kb_access(api_key, str(job["kb_name"]))
    return job


@app.post("/manual-library/rebuild-jobs/{job_id}/cancel")
def cancel_rebuild_job(
    job_id: str,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    queue = _require_rebuild_queue()
    job = queue.get(job_id)
    ensure_kb_access(api_key, job.kb_name)
    cancelled = queue.cancel(job_id)
    return cancelled.to_dict()


@app.post("/manual-library/rebuild-jobs/{job_id}/retry")
def retry_rebuild_job(
    job_id: str,
    api_key: ApiKey = Depends(require_scope("rebuild")),
    _: None = Depends(rate_limit_dep),
):
    queue = _require_rebuild_queue()
    job = queue.get(job_id)
    ensure_kb_access(api_key, job.kb_name)
    retried = queue.retry(job_id)
    return retried.to_dict()


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


def _resolve_indexgen_target_versions(req: IndexGenBuildShadowRequest) -> dict[str, object]:
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


@app.post("/admin/generation/build-shadow")
def admin_build_shadow(
    request: IndexGenBuildShadowRequest,
    _api_key: ApiKey = Depends(require_scope("admin")),
):
    target_versions = _resolve_indexgen_target_versions(request)
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


@app.post("/admin/generation/cancel-shadow")
def admin_cancel_shadow(
    request: IndexGenCancelShadowRequest,
    _api_key: ApiKey = Depends(require_scope("admin")),
):
    return app_state.cancel_shadow_rebuild(request.kb_name, settings)


@app.post("/admin/generation/swap")
def admin_swap_generation(
    request: IndexGenSwapRequest,
    _api_key: ApiKey = Depends(require_scope("admin")),
):
    return app_state.swap_generation(request.kb_name, settings)


@app.post("/admin/generation/retire")
def admin_retire_generation(
    request: IndexGenRetireRequest,
    _api_key: ApiKey = Depends(require_scope("admin")),
):
    return app_state.retire_generation(
        request.kb_name, request.generation, settings, force=request.force
    )


@app.get("/admin/generation/status")
def admin_generation_status(
    kb_name: str = "default",
    _api_key: ApiKey = Depends(require_scope("admin")),
):
    from .indexgen import read_meta

    kb_root = Path(settings.storage.data_dir) / kb_name
    meta = app_state.get_generation_meta(kb_name) or read_meta(kb_root)
    if meta is None:
        raise ServiceError(
            ErrorCode.INDEXGEN_NO_SUCH_KB,
            "KB has no index.json.",
            {"kb_name": kb_name},
        )
    return meta.to_dict()


def _parse_metadata_form(metadata: str) -> dict[str, object]:
    try:
        parsed = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise ServiceError(ErrorCode.INVALID_INPUT, "metadata must be valid JSON.", {"error": str(exc)}) from exc
    if not isinstance(parsed, dict):
        raise ServiceError(ErrorCode.INVALID_INPUT, "metadata must be a JSON object.")
    return parsed


def _parse_rewrite_mode(value: str):
    mode = value.strip().lower()
    if mode not in {"merge", "rename"}:
        raise ServiceError(ErrorCode.INVALID_INPUT, "mode must be merge or rename.", {"mode": value})
    return mode


def _parse_alias_mode(value: str | None):
    if value is None or not str(value).strip():
        return None
    mode = str(value).strip().lower()
    if mode not in {"synonym", "deprecated"}:
        raise ServiceError(ErrorCode.INVALID_INPUT, "policy_alias_mode must be synonym or deprecated.", {"policy_alias_mode": value})
    return mode


def _governed_filter_dict(kb_name: str, filters: SearchFilters | None) -> dict[str, object]:
    filter_dict = filters.to_filter_dict() if filters else {}
    tags = filter_dict.get("tags")
    if isinstance(tags, list) and tags:
        policy = load_tag_policy(kb_name, settings)
        filter_dict["tags"] = resolve_tags_for_search([str(tag) for tag in tags], policy)
    return filter_dict


def _resolved_filter_dict(request: SearchRequest, state: GraphState) -> tuple[dict[str, object], NarrowingDecision]:
    explicit_filters = _governed_filter_dict(request.kb_name, request.filters)
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


def _request_library_rebuild(
    kb_name: str,
    *,
    mode: str,
    allow_fallback: bool,
    trigger: str,
    top_level: bool = False,
) -> dict[str, object]:
    if settings.manual_library.rebuild_queue_enabled:
        queue = _get_rebuild_queue()
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


def _manual_library_diagnostics(
    kb_name: str,
    *,
    verify_blobs: bool,
    include_jobs: bool,
    job_status: str | None,
    api_key: ApiKey,
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
        queue = _get_rebuild_queue()
        jobs = [
            job
            for job in queue.list_jobs(kb_name=kb_name, status=job_status)
            if api_key.allows_kb(str(job.get("kb_name") or ""))
        ]
    queue_payload = {"enabled": settings.manual_library.rebuild_queue_enabled, "jobs": jobs}
    operations = dirty_report.get("operations_summary") if isinstance(dirty_report.get("operations_summary"), dict) else {}
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
        },
        "recommendations": _diagnostic_recommendations(registry, blob_health, dirty_report, jobs),
    }


def _diagnostic_recommendations(
    registry: dict[str, object],
    blob_health: dict[str, object],
    dirty_report: dict[str, object],
    jobs: list[dict[str, object]],
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
    if not registry.get("enabled"):
        recommendations.append({"code": "file_sidecar_mode", "label": "Registry disabled; using file sidecars", "severity": "info"})
    return recommendations


def _safe_audit_detail(detail: dict[str, object]) -> dict[str, object]:
    allowed = {"source_file", "status", "checksum", "blob_backend", "size_bytes", "content_type"}
    return {
        key: value
        for key, value in detail.items()
        if key in allowed and (isinstance(value, (str, int, float, bool)) or value is None)
    }


def _get_rebuild_queue() -> RebuildQueue:
    global rebuild_queue
    if rebuild_queue is None or rebuild_queue.app_state is not app_state or rebuild_queue.cfg is not settings:
        rebuild_queue = RebuildQueue(app_state, settings, embedder=embedder)
    return rebuild_queue


def _require_rebuild_queue() -> RebuildQueue:
    if not settings.manual_library.rebuild_queue_enabled:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Rebuild queue is not enabled.", {})
    return _get_rebuild_queue()
