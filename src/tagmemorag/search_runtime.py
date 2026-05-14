from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from .config import Settings
from .errors import ServiceError
from .lexical_search import lexical_score_map, lexical_search
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
    lexical_candidate_count: int = 0
    lexical_source_count: int = 0
    lexical_profile: str = "disabled"


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
    query_text: str = "",
) -> SearchExecution:
    filter_dict = dict(filters or {})
    filtered_node_ids = filter_node_ids(state.graph, filter_dict)
    eligible_node_ids = filtered_node_ids
    strategy = "exact_local"
    ann_candidate_count = 0
    ann_fallback_reason = ""
    lexical_matches = _lexical_matches(state=state, query=query_text, settings=settings, filtered_node_ids=filtered_node_ids)
    lexical_scores = lexical_score_map(lexical_matches)
    lexical_candidate_ids = set(lexical_scores)

    if _ann_enabled(state, settings):
        ann_result = _ann_eligible_node_ids(
            state=state,
            query_vec=query_vec,
            settings=settings,
            filtered_node_ids=filtered_node_ids,
        )
        if ann_result is not None:
            eligible_node_ids, strategy, ann_candidate_count, ann_fallback_reason = ann_result
            if strategy == "ann_preselect_then_wave" and lexical_candidate_ids:
                eligible_node_ids = set(eligible_node_ids) | lexical_candidate_ids

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
        lexical_scores=lexical_scores,
        lexical_source_k=int(settings.search.lexical_source_k) if settings.search.lexical_enabled else 0,
    )
    return SearchExecution(
        results=results,
        eligible_node_ids=eligible_node_ids,
        strategy=strategy,
        ann_candidate_count=ann_candidate_count,
        ann_fallback_reason=ann_fallback_reason,
        lexical_candidate_count=len(lexical_matches),
        lexical_source_count=min(
            int(settings.search.lexical_source_k),
            len([node_id for node_id in lexical_candidate_ids if node_id in eligible_node_ids]),
        )
        if settings.search.lexical_enabled
        else 0,
        lexical_profile=_lexical_profile(settings),
    )


def search_cache_suffix(settings: Settings, *, has_filters: bool) -> str:
    lexical = _lexical_cache_suffix(settings)
    if not _ann_config_enabled(settings):
        return f"exact_local|{lexical}"
    if settings.search.ann_force_exact_on_filters and has_filters:
        return f"exact_local_force_filters|{lexical}"
    return f"ann_preselect:{int(settings.search.ann_candidate_k)}|{lexical}"


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
        "lexical_enabled": execution.lexical_profile != "disabled",
        "lexical_candidate_count": int(execution.lexical_candidate_count),
        "lexical_source_count": int(execution.lexical_source_count),
        "lexical_profile": execution.lexical_profile,
        "source_k": int(params["source_k"]),
        "steps": int(params["steps"]),
        "aggregate": str(params["aggregate"]),
        "eligible_node_count": len(execution.eligible_node_ids),
    }


def _ann_enabled(state: GraphState, settings: Settings) -> bool:
    return _ann_config_enabled(settings) and settings.vector_store.provider == "qdrant" and state.vectors.shape[0] > 0


def _ann_config_enabled(settings: Settings) -> bool:
    return bool(settings.search.ann_preselect_enabled and settings.search.ann_candidate_k > 0)


def _lexical_matches(
    *,
    state: GraphState,
    query: str,
    settings: Settings,
    filtered_node_ids: set[int],
):
    if not settings.search.lexical_enabled:
        return []
    return lexical_search(
        state.graph,
        query,
        eligible_node_ids=filtered_node_ids,
        candidate_k=int(settings.search.lexical_candidate_k),
        min_token_chars=int(settings.search.lexical_min_token_chars),
        boost=float(settings.search.lexical_boost),
        exact_code_boost=float(settings.search.lexical_exact_code_boost),
        model_boost=float(settings.search.lexical_model_boost),
    )


def _lexical_profile(settings: Settings) -> str:
    if not settings.search.lexical_enabled:
        return "disabled"
    if settings.search.lexical_source_k > 0:
        return "source_boost"
    return "score_boost"


def _lexical_cache_suffix(settings: Settings) -> str:
    return (
        "lexical:"
        f"{int(settings.search.lexical_enabled)}:"
        f"{int(settings.search.lexical_candidate_k)}:"
        f"{int(settings.search.lexical_source_k)}:"
        f"{settings.search.lexical_min_token_chars}:"
        f"{settings.search.lexical_boost:g}:"
        f"{settings.search.lexical_exact_code_boost:g}:"
        f"{settings.search.lexical_model_boost:g}"
    )


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
