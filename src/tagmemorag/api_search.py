from __future__ import annotations

import hashlib
import json
import time

import numpy as np
import structlog
from fastapi import Request

from .answer import create_answer_generator
from .answer.base import AnswerGenerationError, AnswerGenerator, AnswerRequestContext
from .answer.prompt import build_answer_prompt, validate_generation_citations
from .api_manual import resolved_filter_dict
from .api_models import AnswerRequest, QaAnswerRequest, RetrieveRequest, SearchRequest
from .config import Settings
from .errors import ErrorCode, ServiceError
from .observability.metrics import get_metrics
from .observability.tracing import set_span_attributes, start_span
from .qa_context import context_meta, contextual_question, normalize_question, trim_context_text
from .retrieval import VisualEvidenceResolver, build_retrieve_response, retrieve_inspect_payload
from .retrieval import VisualRetrievalResolver
from .search_runtime import (
    execute_search,
    search_ann_enabled,
    search_cache_suffix,
    search_debug_enabled,
    search_debug_payload,
)
from .state import AppState
from .types import GraphState
from .visual_retrieval import create_visual_components
from .wave_searcher import normalize_filters
from .wave_tag_spike import GhostTag
from .document_assets import load_asset_manifest

settings: Settings
app_state: AppState
embedder = None
execute_search_fn = execute_search
answer_generator_override = None


def configure(
    runtime_settings: Settings,
    runtime_app_state: AppState,
    runtime_embedder,
    *,
    runtime_execute_search=execute_search,
    runtime_answer_generator=None,
) -> None:
    global settings, app_state, embedder, execute_search_fn, answer_generator_override
    settings = runtime_settings
    app_state = runtime_app_state
    embedder = runtime_embedder
    execute_search_fn = runtime_execute_search
    answer_generator_override = runtime_answer_generator


def normalize_question_for_cache(question: str) -> str:
    return normalize_question(question)


def trim_context_text_for_api(value: str | None, limit: int) -> str:
    return trim_context_text(value, limit)


def qa_contextual_question(request: QaAnswerRequest) -> str:
    return contextual_question(request.question, list(request.conversation_context))


def qa_context_meta(request: QaAnswerRequest) -> dict[str, object]:
    return context_meta(list(request.conversation_context))


def search_param_values(request: SearchRequest) -> dict[str, object]:
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


def spotlight_cache_suffix(request: SearchRequest) -> str:
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


def compute_cache_key(request: SearchRequest, state: GraphState) -> str:
    params = search_param_values(request)
    filter_dict, _narrowing = resolved_filter_dict(request, state, settings)
    canonical_filters = normalize_filters(filter_dict)
    strategy_suffix = search_cache_suffix(settings, has_filters=bool(canonical_filters))
    debug_suffix = f"debug:{int(search_debug_enabled(request.debug, settings))}"
    spotlight_suffix = spotlight_cache_suffix(request)
    parts = [
        request.kb_name,
        state.build_id,
        str(state.anchors_version),
        normalize_question_for_cache(request.question),
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


def compute_search_id(request: SearchRequest, state: GraphState, trace_id: str) -> str:
    params = search_param_values(request)
    filter_dict, _narrowing = resolved_filter_dict(request, state, settings)
    canonical_filters = normalize_filters(filter_dict)
    strategy_suffix = search_cache_suffix(settings, has_filters=bool(canonical_filters))
    debug_suffix = f"debug:{int(search_debug_enabled(request.debug, settings))}"
    spotlight_suffix = spotlight_cache_suffix(request)
    parts = [
        state.kb_name,
        state.build_id,
        trace_id,
        normalize_question_for_cache(request.question),
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


def compute_retrieve_id(request: RetrieveRequest, state: GraphState, trace_id: str) -> str:
    base = compute_search_id(request, state, trace_id)
    parts = ["retrieve", base, str(int(request.token_budget))]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def build_and_log_plan(request: SearchRequest, state: GraphState):
    """T2: construct QueryPlan + insert basic row. Returns (plan, plan_log).

    Caller is responsible for calling plan_log.update_result_async() before
    returning the response to fill in result columns.
    """
    from .queryplan import PlanLog, build_plan
    from .agentic.surface import resolve_agentic_mode, stamp_plan_mode

    filter_dict, _narrowing = resolved_filter_dict(request, state, settings)
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


def served_by_generation(state: GraphState) -> int | None:
    """T2: Try to read served_by_generation from state.meta; falls back to None
    when index.json is not yet wired into rebuilds."""
    if not isinstance(state.meta, dict):
        return None
    gen = state.meta.get("served_by_generation")
    return int(gen) if gen is not None else None


_RERANK_DISPATCHER_CACHE: dict[int, "object"] = {}


def rerank_dispatcher():
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


def reorder_results(original_results, rerank_outcome):
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


def search_impl(request: SearchRequest, http_request: Request, state: GraphState, t0: float):
    plan, plan_log = build_and_log_plan(request, state)
    warnings: list[str] = []

    # Out-of-scope short-circuit (T2 D2): skip retrieval, return empty results,
    # still write plan log so we can study these queries later.
    from .queryplan import Intent

    if plan.intent == Intent.OUT_OF_SCOPE:
        warnings.append("out_of_scope_intent")
        trace_id = str(getattr(http_request.state, "trace_id", ""))
        search_id = compute_search_id(request, state, trace_id)
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
            "served_by_generation": served_by_generation(state),
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
    cache_key = compute_cache_key(request, state)
    cache = app_state.query_cache if settings.cache.enabled else None
    with start_span("tagmemorag.search.cache", **{"tagmemorag.kb_name": state.kb_name}):
        cached = cache.get(cache_key) if cache is not None else None
        cache_status = "hit" if cached is not None else ("miss" if cache is not None else "disabled")
        set_span_attributes(**{"tagmemorag.cache_status": cache_status})
    get_metrics().record_cache_operation(operation="get", outcome=cache_status)
    if cached is not None:
        search_time_ms = (time.perf_counter() - t0) * 1000.0
        trace_id = str(getattr(http_request.state, "trace_id", ""))
        search_id = compute_search_id(request, state, trace_id)
        payload = {**cached, "trace_id": trace_id, "search_id": search_id, "search_time_ms": round(search_time_ms, 3), "cache": "hit", "plan_id": plan.plan_id}
        result_count = len(payload.get("results", []))
        plan_log.update_result_async(plan.plan_id, {
            "served_by_generation": served_by_generation(state),
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
    params = search_param_values(request)
    aggregate = str(params["aggregate"])
    if aggregate not in {"max", "sum"}:
        raise ServiceError(
            ErrorCode.INVALID_INPUT,
            "aggregate must be 'max' or 'sum'.",
            {"aggregate": aggregate},
        )
    with start_span("tagmemorag.search.wave", **{"tagmemorag.kb_name": state.kb_name}):
        filter_dict, narrowing = resolved_filter_dict(request, state, settings)
        ghost_tag_args = tuple(
            GhostTag(
                name=str(g.name),
                vector=np.asarray(g.vector, dtype=np.float32),
                is_core=bool(g.is_core),
            )
            for g in request.ghost_tags
        )
        execution = execute_search_fn(
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
        "search_id": compute_search_id(request, state, trace_id),
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
        "served_by_generation": served_by_generation(state),
        "served_by_build_id": state.build_id,
        "cache_status": cache_status,
        "evidence_ids": [r.id for r in results if hasattr(r, "id")],
        "latency_ms_observed": int(search_time_ms),
        "warnings": list(warnings),
    })
    return payload


def build_answer_response(request: AnswerRequest, retrieve_payload: dict) -> dict:
    warnings = list(retrieve_payload.get("warnings") or [])
    answerability = dict(retrieve_payload.get("answerability") or {})
    if not bool(answerability.get("answerable")):
        reason = str(answerability.get("fallback_reason") or "insufficient_evidence")
        answer_obj = answer_error_obj(
            kind="refusal",
            reason=reason,
            warning=f"answer_refused:{reason}",
            confidence=float(answerability.get("confidence") or 0.0),
            missing_evidence_hints=[reason],
        )
        warnings.append(f"answer_refused:{reason}")
        return answer_response_payload(request, retrieve_payload, answer_obj, warnings)

    if not settings.answer.enabled:
        answer_obj = answer_error_obj(
            kind="error",
            reason="generation_disabled",
            warning="answer_generation_disabled",
            confidence=float(answerability.get("confidence") or 0.0),
            missing_evidence_hints=[],
        )
        warnings.append("answer_generation_disabled")
        return answer_response_payload(request, retrieve_payload, answer_obj, warnings)

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
        generation = answer_generator().generate(context)
        cleaned = validate_generation_citations(generation, prompt.allowed_citation_ids)
        answer_obj = cleaned.to_answer_dict(confidence=float(answerability.get("confidence") or 0.0))
        warnings.extend(cleaned.warnings)
    except (AnswerGenerationError, ServiceError, ValueError) as exc:
        reason = type(exc).__name__
        answer_obj = answer_error_obj(
            kind="error",
            reason="generation_failed",
            warning=f"answer_generation_failed:{reason}",
            confidence=float(answerability.get("confidence") or 0.0),
            missing_evidence_hints=[],
        )
        warnings.append(f"answer_generation_failed:{reason}")
    return answer_response_payload(request, retrieve_payload, answer_obj, warnings)


def answer_error_obj(
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


def answer_response_payload(request: AnswerRequest, retrieve_payload: dict, answer_obj: dict, warnings: list[str]) -> dict:
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


def answer_generator() -> AnswerGenerator:
    if answer_generator_override is not None:
        return answer_generator_override()
    key = id(settings)
    cached = _ANSWER_GENERATOR_CACHE.get(key)
    if cached is None:
        cached = create_answer_generator(settings)
        _ANSWER_GENERATOR_CACHE[key] = cached
    return cached


def retrieve_impl(request: RetrieveRequest, http_request: Request, state: GraphState, t0: float):
    plan, plan_log = build_and_log_plan(request, state)
    warnings: list[str] = []

    # Out-of-scope short-circuit (T2 D2)
    from .queryplan import Intent
    from .queryplan.budget import BudgetGuard

    if plan.intent == Intent.OUT_OF_SCOPE:
        warnings.append("out_of_scope_intent")
        trace_id = str(getattr(http_request.state, "trace_id", ""))
        search_id = compute_search_id(request, state, trace_id)
        retrieve_id = compute_retrieve_id(request, state, trace_id)
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
            "served_by_generation": served_by_generation(state),
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
    params = search_param_values(request)
    aggregate = str(params["aggregate"])
    if aggregate not in {"max", "sum"}:
        raise ServiceError(
            ErrorCode.INVALID_INPUT,
            "aggregate must be 'max' or 'sum'.",
            {"aggregate": aggregate},
        )
    with start_span("tagmemorag.retrieve.wave", **{"tagmemorag.kb_name": state.kb_name}):
        filter_dict, narrowing = resolved_filter_dict(request, state, settings)
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
        execution = execute_search_fn(
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
        rerank_outcome = rerank_dispatcher().rerank(
            plan,
            list(execution.results),
            guard,
            query_text=request.question,
        )
        if rerank_outcome.warnings:
            warnings.extend(rerank_outcome.warnings)
        candidates_used = reorder_results(execution.results, rerank_outcome)
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
    search_id = compute_search_id(request, state, trace_id)
    asset_manifest = load_asset_manifest(state.kb_name, settings) if settings.assets.enabled else None
    visual_provider, visual_reranker = create_visual_components(settings)
    payload = build_retrieve_response(
        results=candidates_used,
        build_id=state.build_id,
        kb_name=state.kb_name,
        trace_id=trace_id,
        search_id=search_id,
        retrieve_id=compute_retrieve_id(request, state, trace_id),
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
        "served_by_generation": served_by_generation(state),
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
