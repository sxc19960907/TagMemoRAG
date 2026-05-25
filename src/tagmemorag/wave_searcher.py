from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal, Mapping

import networkx as nx
import numpy as np

from .lexical_search import lexical_evidence_score
from .manuals import manual_result_fields, metadata_from_node, normalize_tag
from .types import Anchor, Result


def wave_search(
    query_vec: np.ndarray,
    graph: nx.Graph,
    vectors: np.ndarray,
    anchors: dict[int, Anchor] | None = None,
    top_k: int = 5,
    source_k: int = 3,
    steps: int = 3,
    decay: float = 0.7,
    amplitude_cutoff: float = 0.01,
    aggregate: Literal["max", "sum"] = "max",
    eligible_node_ids: set[int] | None = None,
    filters: Mapping[str, Any] | None = None,
    boost_filters: Mapping[str, Any] | None = None,
    metadata_field_boost: float = 0.0,
    tag_boost: float = 0.0,
    lexical_scores: Mapping[int, float] | None = None,
    lexical_source_k: int = 0,
    query_text: str = "",
    lexical_min_token_chars: int = 2,
    *,
    disable_legacy_tag_boost: bool = False,
    rerank_pool_size: int | None = None,
) -> list[Result]:
    anchors = anchors or {}
    if aggregate not in {"max", "sum"}:
        raise ValueError("aggregate must be 'max' or 'sum'")
    if graph.number_of_nodes() == 0:
        return []
    if vectors.shape[0] != graph.number_of_nodes():
        raise ValueError("vectors row count must match graph nodes")

    eligible = set(graph.nodes) if eligible_node_ids is None else set(eligible_node_ids)
    if not eligible:
        return []

    sims = vectors @ query_vec
    ranked_source_ids = sorted(eligible, key=lambda node_id: (-float(sims[node_id]), int(node_id)))
    source_ids = ranked_source_ids[: min(source_k, len(ranked_source_ids))]
    lexical_scores = dict(lexical_scores or {})
    if lexical_source_k > 0 and lexical_scores:
        lexical_source_ids = sorted(
            (node_id for node_id in eligible if node_id in lexical_scores and node_id not in source_ids),
            key=lambda node_id: (-float(lexical_scores[node_id]), int(node_id)),
        )
        source_ids.extend(lexical_source_ids[: min(lexical_source_k, len(lexical_source_ids))])

    amplitudes: defaultdict[int, float] = defaultdict(float)
    current_wave: dict[int, float] = {}
    for nid in source_ids:
        node_id = int(nid)
        amp = max(float(sims[node_id]), float(lexical_scores.get(node_id, 0.0)))
        if node_id in anchors:
            amp *= anchors[node_id].boost
        if aggregate == "max":
            amplitudes[node_id] = max(amplitudes[node_id], amp)
            current_wave[node_id] = max(current_wave.get(node_id, 0.0), amp)
        else:
            amplitudes[node_id] += amp
            current_wave[node_id] = current_wave.get(node_id, 0.0) + amp

    for _ in range(steps):
        next_wave: dict[int, float] = {}
        for node_id, amp in current_wave.items():
            if amp < amplitude_cutoff:
                continue
            prop_amp = amp
            if node_id in anchors:
                prop_amp *= anchors[node_id].propagation_boost
            for neighbor, attrs in graph[node_id].items():
                if neighbor not in eligible:
                    continue
                new_amp = prop_amp * float(attrs["weight"]) * decay
                if new_amp < amplitude_cutoff:
                    continue
                if aggregate == "max":
                    next_wave[neighbor] = max(next_wave.get(neighbor, 0.0), new_amp)
                else:
                    next_wave[neighbor] = next_wave.get(neighbor, 0.0) + new_amp
        for node_id, amp in next_wave.items():
            if aggregate == "max":
                amplitudes[node_id] = max(amplitudes[node_id], amp)
            else:
                amplitudes[node_id] += amp
        current_wave = next_wave

    normalized_filters = normalize_filters(filters)
    normalized_boost_filters = {**normalized_filters, **normalize_filters(boost_filters)}
    effective_tag_boost = 0.0 if disable_legacy_tag_boost else tag_boost
    boosted = {
        node_id: _apply_lexical_boost(
            _apply_metadata_boost(
                score,
                metadata_from_node(graph.nodes[node_id]),
                normalized_boost_filters,
                metadata_field_boost=metadata_field_boost,
                tag_boost=effective_tag_boost,
            ),
            lexical_scores.get(node_id, 0.0),
        )
        for node_id, score in amplitudes.items()
    }
    ranked = _rank_boosted_results(
        graph,
        boosted,
        query_text=query_text,
        lexical_min_token_chars=lexical_min_token_chars,
    )
    limit = top_k if rerank_pool_size is None else max(int(rerank_pool_size), 0)
    ranked = ranked[:limit]
    return [_make_result(graph, node_id, score) for node_id, score in ranked]


def _rank_boosted_results(
    graph: nx.Graph,
    boosted: Mapping[int, float],
    *,
    query_text: str = "",
    lexical_min_token_chars: int = 2,
) -> list[tuple[int, float]]:
    if not query_text.strip():
        return sorted(boosted.items(), key=lambda item: (-item[1], item[0]))
    evidence_scores = {
        int(node_id): lexical_evidence_score(
            query_text,
            graph.nodes[node_id],
            min_token_chars=lexical_min_token_chars,
        )
        for node_id in boosted
    }
    return sorted(
        boosted.items(),
        key=lambda item: (
            -float(item[1]),
            -evidence_scores[int(item[0])],
            item[0],
        ),
    )


def _apply_lexical_boost(score: float, lexical_score: float) -> float:
    return float(score) + max(0.0, float(lexical_score))


def filter_node_ids(graph: nx.Graph, filters: Mapping[str, Any] | None = None) -> set[int]:
    normalized = normalize_filters(filters)
    if not normalized:
        return set(graph.nodes)
    eligible: set[int] = set()
    scalar_fields = ("manual_id", "brand", "product_category", "product_model", "language")
    requested_tags = set(normalized.get("tags", []))
    for node_id, node in graph.nodes(data=True):
        metadata = metadata_from_node(node)
        if any(str(metadata.get(field, "")).lower() != normalized[field] for field in scalar_fields if field in normalized):
            continue
        if requested_tags:
            node_tags = metadata.get("tags", [])
            if not isinstance(node_tags, list):
                node_tags = []
            if not requested_tags.intersection(str(tag).lower() for tag in node_tags):
                continue
        eligible.add(int(node_id))
    return eligible


def normalize_filters(filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not filters:
        return {}
    normalized: dict[str, Any] = {}
    for field in ("manual_id", "brand", "product_category", "product_model", "language"):
        value = filters.get(field)
        if value is not None and str(value).strip():
            normalized[field] = str(value).strip().lower()
    tags = filters.get("tags")
    if tags:
        if isinstance(tags, str):
            tags = [tags]
        normalized_tags = sorted({normalize_tag(str(tag)) for tag in tags if normalize_tag(str(tag))})
        if normalized_tags:
            normalized["tags"] = normalized_tags
    return normalized


def _apply_metadata_boost(
    score: float,
    metadata: dict[str, Any],
    filters: Mapping[str, Any],
    *,
    metadata_field_boost: float,
    tag_boost: float,
) -> float:
    if not filters:
        return float(score)
    final_score = float(score)
    for field in ("manual_id", "brand", "product_category", "product_model", "language"):
        if field in filters and str(metadata.get(field, "")).lower() == filters[field]:
            final_score += metadata_field_boost
    requested_tags = set(filters.get("tags", []))
    if requested_tags:
        node_tags = metadata.get("tags", [])
        if isinstance(node_tags, list):
            final_score += len(requested_tags.intersection(str(tag).lower() for tag in node_tags)) * tag_boost
    return final_score


def _make_result(graph: nx.Graph, node_id: int, score: float) -> Result:
    node = graph.nodes[node_id]
    metadata = metadata_from_node(node)
    result_fields = manual_result_fields(metadata)
    return Result(
        node_id=node_id,
        score=float(score),
        text=str(node.get("text", "")),
        header=str(node.get("header", "")),
        path=list(node.get("path", [])),
        source_file=str(node.get("source_file", "")),
        start_line=int(node.get("start_line", 0)),
        anchor_key=str(node.get("anchor_key", "")),
        metadata=metadata,
        **result_fields,
    )
