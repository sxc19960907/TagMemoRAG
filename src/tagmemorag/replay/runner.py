from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ..embedder import create_embedder
from ..retrieval import build_retrieve_response
from ..search_runtime import execute_search
from ..types import GraphState
from .models import ReplayCaseResult, ReplayPlan

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings


def replay_plans(
    *,
    plans: list[ReplayPlan],
    state: GraphState,
    settings: "Settings",
    generation: int,
) -> list[ReplayCaseResult]:
    """Replay plans against a loaded generation state."""
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
    return [
        replay_plan(plan=plan, state=state, settings=settings, generation=generation, embedder=embedder)
        for plan in plans
    ]


def replay_plan(
    *,
    plan: ReplayPlan,
    state: GraphState,
    settings: "Settings",
    generation: int,
    embedder,
) -> ReplayCaseResult:
    started = time.perf_counter()
    try:
        query_vec = embedder.encode_query(plan.query)
        top_k = int(plan.budget.get("max_evidence") or settings.search.top_k or 5)
        execution = execute_search(
            state=state,
            query_vec=query_vec,
            settings=settings,
            query_text=plan.query,
            top_k=top_k,
            source_k=int(settings.search.source_k),
            steps=int(settings.search.steps),
            decay=float(settings.search.decay),
            amplitude_cutoff=float(settings.search.amplitude_cutoff),
            aggregate=str(settings.search.aggregate),
            filters=plan.filters,
            boost_filters=None,
            core_tags=(),
            ghost_tags=(),
        )
        payload = build_retrieve_response(
            results=execution.results,
            build_id=state.build_id,
            kb_name=state.kb_name,
            trace_id="replay",
            search_id=f"replay-search-{plan.plan_id}",
            retrieve_id=f"replay-retrieve-{plan.plan_id}",
            token_budget=int(plan.budget.get("max_evidence") or settings.queryplan.default_max_evidence) * 1000,
            search_time_ms=(time.perf_counter() - started) * 1000.0,
            query_text=plan.query,
        )
        evidence = list(payload.get("evidence") or [])
        chunk_ids = tuple(str(item.get("chunk_id") or "") for item in evidence)
        evidence_ids = tuple(str(item.get("evidence_id") or "") for item in evidence)
        return ReplayCaseResult(
            plan_id=plan.plan_id,
            generation=int(generation),
            query_replayed=True,
            result_count=len(execution.results),
            top_chunk_id=chunk_ids[0] if chunk_ids else "",
            top_evidence_id=evidence_ids[0] if evidence_ids else "",
            chunk_ids=tuple(cid for cid in chunk_ids if cid),
            evidence_ids=tuple(eid for eid in evidence_ids if eid),
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
    except Exception as exc:  # noqa: BLE001
        return ReplayCaseResult(
            plan_id=plan.plan_id,
            generation=int(generation),
            query_replayed=False,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            error=f"{type(exc).__name__}: {exc}",
        )


__all__ = ["replay_plan", "replay_plans"]
