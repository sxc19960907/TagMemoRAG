from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from .config import Settings
from .errors import ServiceError
from .state import _vector_store
from .types import GraphState
from .wave_searcher import filter_node_ids, wave_search


@dataclass(frozen=True)
class SearchExecution:
    results: list[Any]
    eligible_node_ids: set[int]
    strategy: str
    ann_candidate_count: int = 0
    ann_fallback_reason: str = ""


def execute_search(
    *,
    state: GraphState,
    query_vec: np.ndarray,
    settings: Settings,
    top_k: int,
    source_k: int,
    steps: int,
    decay: float,
    amplitude_cutoff: float,
    aggregate: str,
    filters: Mapping[str, Any] | None = None,
) -> SearchExecution:
    filter_dict = dict(filters or {})
    filtered_node_ids = filter_node_ids(state.graph, filter_dict)
    eligible_node_ids = filtered_node_ids
    strategy = "exact_local"
    ann_candidate_count = 0
    ann_fallback_reason = ""

    if _ann_enabled(state, settings):
        ann_result = _ann_eligible_node_ids(
            state=state,
            query_vec=query_vec,
            settings=settings,
            filtered_node_ids=filtered_node_ids,
        )
        if ann_result is not None:
            eligible_node_ids, strategy, ann_candidate_count, ann_fallback_reason = ann_result

    results = wave_search(
        query_vec,
        state.graph,
        state.vectors,
        state.anchors,
        top_k=top_k,
        source_k=source_k,
        steps=steps,
        decay=decay,
        amplitude_cutoff=amplitude_cutoff,
        aggregate=aggregate,  # type: ignore[arg-type]
        eligible_node_ids=eligible_node_ids,
        filters=filter_dict,
        metadata_field_boost=settings.search.metadata_field_boost,
        tag_boost=settings.search.tag_boost,
    )
    return SearchExecution(
        results=results,
        eligible_node_ids=eligible_node_ids,
        strategy=strategy,
        ann_candidate_count=ann_candidate_count,
        ann_fallback_reason=ann_fallback_reason,
    )


def search_cache_suffix(settings: Settings, *, has_filters: bool) -> str:
    if not _ann_config_enabled(settings):
        return "exact_local"
    if settings.search.ann_force_exact_on_filters and has_filters:
        return "exact_local_force_filters"
    return f"ann_preselect:{int(settings.search.ann_candidate_k)}"


def search_debug_enabled(request_debug: bool | None, settings: Settings) -> bool:
    return bool(request_debug) or bool(settings.search.debug_metadata_enabled)


def search_ann_enabled(state: GraphState, settings: Settings) -> bool:
    return _ann_enabled(state, settings)


def search_debug_payload(
    execution: SearchExecution,
    params: Mapping[str, object],
    *,
    ann_enabled: bool,
) -> dict[str, object]:
    return {
        "search_strategy": execution.strategy,
        "ann_enabled": bool(ann_enabled),
        "ann_candidate_count": int(execution.ann_candidate_count),
        "ann_fallback_reason": execution.ann_fallback_reason or "",
        "source_k": int(params["source_k"]),
        "steps": int(params["steps"]),
        "aggregate": str(params["aggregate"]),
        "eligible_node_count": len(execution.eligible_node_ids),
    }


def _ann_enabled(state: GraphState, settings: Settings) -> bool:
    return _ann_config_enabled(settings) and settings.vector_store.provider == "qdrant" and state.vectors.shape[0] > 0


def _ann_config_enabled(settings: Settings) -> bool:
    return bool(settings.search.ann_preselect_enabled and settings.search.ann_candidate_k > 0)


def _ann_eligible_node_ids(
    *,
    state: GraphState,
    query_vec: np.ndarray,
    settings: Settings,
    filtered_node_ids: set[int],
) -> tuple[set[int], str, int, str] | None:
    if settings.search.ann_force_exact_on_filters and filtered_node_ids != set(state.graph.nodes):
        return set(filtered_node_ids), "exact_local", 0, "filters_force_exact"
    try:
        store = _vector_store(state.kb_name, settings, dim=state.vectors.shape[1] if state.vectors.ndim == 2 else settings.model.dim)
        candidates = store.search_candidates(query_vec, int(settings.search.ann_candidate_k))
    except (AttributeError, NotImplementedError):
        return set(filtered_node_ids), "exact_local", 0, "ann_unavailable"
    except ServiceError:
        return set(filtered_node_ids), "exact_local", 0, "ann_query_failed"

    valid_node_ids = {int(node_id) for node_id in state.graph.nodes}
    candidate_node_ids = [node_id for node_id, _score in candidates if node_id in valid_node_ids]
    if len(candidate_node_ids) != len(candidates):
        return set(filtered_node_ids), "exact_local", 0, "candidate_ids_invalid"

    filtered_candidates = set(candidate_node_ids) & set(filtered_node_ids)
    anchor_ids = {int(node_id) for node_id in state.anchors if int(node_id) in filtered_node_ids}
    eligible = filtered_candidates | anchor_ids
    if not eligible:
        return set(filtered_node_ids), "exact_local", 0, "filtered_candidates_too_small"
    return eligible, "ann_preselect_then_wave", len(candidate_node_ids), ""
