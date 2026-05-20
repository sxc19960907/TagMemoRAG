"""Experimental Phase 4: V8 geodesicRerank on wave_search candidates.

Source: VCPToolBox TagMemoEngine.geodesicRerank (TagMemoEngine.js:537-640).
Default status: off. The 2026-05-17 WAVE readiness check kept this flag off
because fixture results were mixed; promotion requires explicit eval evidence.

Algorithm overview
------------------
For each candidate chunk in the input list, look up its `metadata.tags`,
resolve each tag name to a `tag_id`, and accumulate the tag-energy field
(produced earlier by `wave_tag_spike.propagate`) across the candidate's tags.
The geo score is the mean energy per hit tag (`total / hits`). Candidates
with `hits < min_geo_samples` are zeroed (L1). After normalizing by `max_geo`
across all candidates, the final score blends:

    final = (1 - alpha) * knn_score + alpha * normalized_geo

Three-layer fallback (matches source-side defense):

* L0  — energy_field is empty / None  ⇒ return input order verbatim.
* L1  — per-candidate hit count below `min_geo_samples` ⇒ that geoScore = 0.
* L2  — global `max_geo == 0`  ⇒ return input order verbatim.

This module does NOT mutate the input candidates. It returns a new list with
optional diagnostic fields attached via `Result.metadata`.

Phase 4.1 extension point: `_score_aggregator` is hard-coded to mean today;
swap it for a strategy lookup (sum / log_norm / max_pool) when needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping, Sequence

import networkx as nx

from .config import Settings
from .manual_registry import create_registry
from .manuals import metadata_from_node, normalize_tag
from .tag_store import iter_canonical_tags_with_vectors
from .types import Result


def _phase0_registry_path(cfg: Settings):
    """Mirror the helper defined in wave_tag_spike / epa_basis / tag_governance.

    Each module redefines this locally to avoid leaking a private symbol across
    module boundaries (the leading underscore is intentional). When the path
    resolution rule changes, all four redefinitions must be updated together.
    """
    if cfg.manual_library.registry_path == "data/manual_registry.sqlite3":
        return Path(cfg.storage.data_dir) / "manual_registry.sqlite3"
    return cfg.manual_library.registry_path


_ZERO_SWAPS: dict[str, int] = {"rank_changed": 0, "new_entry": 0, "lost_entry": 0}


@dataclass(frozen=True)
class GeodesicRerankResult:
    """Return value of `geodesic_rerank`.

    `applied=True` iff V8 actually contributed to ranking (skipped_reason is None
    AND max_geo > 0). `swap_kinds` summarizes how `top_k` differs before/after.
    """

    candidates: list[Result]
    swap_kinds: dict[str, int] = field(default_factory=lambda: dict(_ZERO_SWAPS))
    skipped_reason: str | None = None
    hit_count_observed: tuple[int, ...] = ()
    max_geo: float = 0.0
    applied: bool = False


def _score_aggregator(total: float, hits: int) -> float:
    # Phase 4.1: replace with strategy lookup (mean / sum / log_norm / max_pool).
    if hits <= 0:
        return 0.0
    return float(total) / float(hits)


def _build_tag_name_to_id_map(settings: Settings, kb_name: str) -> dict[str, int]:
    """Build a name→id map for the KB's canonical tags.

    Used once per `geodesic_rerank` call to avoid per-candidate SQL hits.
    Returns empty dict on any registry error (V8 falls through to max_geo=0).
    """
    try:
        registry = create_registry(_phase0_registry_path(settings))
        with registry.connection() as conn:
            return {tag.name: int(tag.id) for tag in iter_canonical_tags_with_vectors(conn, kb_name=kb_name)}
    except Exception:
        return {}


def _resolve_chunk_tag_ids(
    graph: nx.Graph,
    node_id: int,
    *,
    name_to_id: Mapping[str, int],
) -> list[int]:
    """Read a chunk's `metadata.tags` and resolve each name to a tag_id.

    Unknown / unnormalized tags are silently skipped — the caller treats them
    as `hitCount` decrements rather than failures.
    """
    metadata = metadata_from_node(graph.nodes[node_id])
    raw_tags = metadata.get("tags") or []
    if not isinstance(raw_tags, list):
        return []
    resolved: list[int] = []
    for raw in raw_tags:
        name = normalize_tag(str(raw))
        tag_id = name_to_id.get(name)
        if tag_id is not None:
            resolved.append(tag_id)
    return resolved


def _attach_diagnostics(
    candidate: Result,
    *,
    new_score: float,
    original_knn_score: float,
    geo_score: float,
    normalized_geo: float,
    geo_hit_count: int,
) -> Result:
    """Return a new Result with V8 diagnostic fields attached to metadata."""
    new_metadata = dict(candidate.metadata)
    new_metadata.update(
        {
            "geodesic_original_knn_score": float(original_knn_score),
            "geodesic_geo_score": float(geo_score),
            "geodesic_normalized_geo": float(normalized_geo),
            "geodesic_hit_count": int(geo_hit_count),
        }
    )
    return replace(candidate, score=float(new_score), metadata=new_metadata)


def geodesic_rerank(
    candidates: Sequence[Result],
    *,
    energy_field: Mapping[int, float] | None,
    graph: nx.Graph,
    kb_name: str,
    settings: Settings,
    top_k: int,
    alpha: float | None = None,
    min_geo_samples: int | None = None,
) -> GeodesicRerankResult:
    """Rerank candidates by tag-energy mean (V8 geodesicRerank).

    Returns a new list (input is never mutated). When the algorithm degrades
    to noop via L0/L2, the input order is preserved verbatim and
    `skipped_reason` is set; callers should record the reason as a metric.
    """
    cfg = settings.wave_phase1
    eff_alpha = float(alpha) if alpha is not None else float(cfg.geodesic_alpha)
    eff_alpha = max(0.0, min(1.0, eff_alpha))
    eff_min = int(min_geo_samples) if min_geo_samples is not None else int(cfg.geodesic_min_geo_samples)
    eff_min = max(1, eff_min)

    # L0 — empty / missing energy field
    if not energy_field:
        return GeodesicRerankResult(
            candidates=list(candidates),
            swap_kinds=dict(_ZERO_SWAPS),
            skipped_reason="energy_field_empty",
            hit_count_observed=(),
            max_geo=0.0,
            applied=False,
        )
    if not candidates:
        return GeodesicRerankResult(
            candidates=[],
            swap_kinds=dict(_ZERO_SWAPS),
            skipped_reason="no_candidates",
            hit_count_observed=(),
            max_geo=0.0,
            applied=False,
        )

    name_to_id = _build_tag_name_to_id_map(settings, kb_name)

    # Per-candidate geo score (with L1 zero-out)
    geo_data: list[tuple[Result, float, int, float]] = []
    hit_counts: list[int] = []
    max_geo = 0.0
    for cand in candidates:
        tag_ids = _resolve_chunk_tag_ids(graph, cand.node_id, name_to_id=name_to_id)
        total = 0.0
        hits = 0
        for tid in tag_ids:
            energy = energy_field.get(int(tid))
            if energy is not None:
                total += float(energy)
                hits += 1
        geo_score = _score_aggregator(total, hits) if hits >= eff_min else 0.0
        if geo_score > max_geo:
            max_geo = geo_score
        geo_data.append((cand, geo_score, hits, total))
        hit_counts.append(hits)

    # L2 — global max_geo == 0 ⇒ noop
    if max_geo <= 0.0:
        return GeodesicRerankResult(
            candidates=list(candidates),
            swap_kinds=dict(_ZERO_SWAPS),
            skipped_reason="max_geo_zero",
            hit_count_observed=tuple(hit_counts),
            max_geo=0.0,
            applied=False,
        )

    # Blend + sort
    reranked: list[Result] = []
    for cand, geo, hits, _total in geo_data:
        norm_geo = geo / max_geo
        knn = float(cand.score)
        final = (1.0 - eff_alpha) * knn + eff_alpha * norm_geo
        reranked.append(
            _attach_diagnostics(
                cand,
                new_score=final,
                original_knn_score=knn,
                geo_score=geo,
                normalized_geo=norm_geo,
                geo_hit_count=hits,
            )
        )
    reranked.sort(key=lambda r: (-r.score, r.node_id))

    # Compute swap_kinds against the input top_k
    effective_k = max(1, min(int(top_k), len(candidates)))
    before_top = [c.node_id for c in candidates[:effective_k]]
    after_top = [r.node_id for r in reranked[:effective_k]]
    before_set = set(before_top)
    after_set = set(after_top)
    new_entry = len(after_set - before_set)
    lost_entry = len(before_set - after_set)
    rank_changed = sum(
        1
        for i, nid in enumerate(after_top)
        if nid in before_set and (i >= len(before_top) or before_top[i] != nid)
    )

    return GeodesicRerankResult(
        candidates=reranked,
        swap_kinds={
            "rank_changed": int(rank_changed),
            "new_entry": int(new_entry),
            "lost_entry": int(lost_entry),
        },
        skipped_reason=None,
        hit_count_observed=tuple(hit_counts),
        max_geo=float(max_geo),
        applied=True,
    )
