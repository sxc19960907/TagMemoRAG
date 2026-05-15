from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import threading
from typing import Mapping

import numpy as np

from .config import Settings
from .manual_registry import create_registry
from .tag_cooccurrence import (
    CooccurrenceMatrix,
    cooccurrence_path,
    load_cooccurrence,
)
from .tag_store import iter_canonical_tags_with_vectors


# Source defaults from VCPToolBox TagMemoEngine.js:187-195 (V6 spike propagation).
SPIKE_MAX_HOPS = 4
SPIKE_BASE_MOMENTUM = 2.0
SPIKE_FIRING_THRESHOLD = 0.10
SPIKE_BASE_DECAY = 0.25
SPIKE_WORMHOLE_DECAY = 0.70
SPIKE_TENSION_THRESHOLD = 1.0
SPIKE_MAX_EMERGENT_NODES = 50
SPIKE_MAX_NEIGHBORS_PER_NODE = 20

# Hardcoded gate constants from the source body (not configurable in srConfig):
_INJECTED_CURRENT_MIN = 0.01
_PROPAGATION_PULSE_MIN = 0.01


@dataclass(frozen=True)
class SpikeResult:
    accumulated_energy: dict[int, float]
    seed_count: int
    emergent_count: int
    hops_executed: int
    truncated_by_cap: bool
    seed_ids: frozenset[int] = field(default_factory=frozenset)


def propagate(
    seed_weights: Mapping[int, float],
    matrix: CooccurrenceMatrix,
    *,
    residuals: Mapping[int, float] | None = None,
    max_hops: int = SPIKE_MAX_HOPS,
    base_momentum: float = SPIKE_BASE_MOMENTUM,
    firing_threshold: float = SPIKE_FIRING_THRESHOLD,
    base_decay: float = SPIKE_BASE_DECAY,
    wormhole_decay: float = SPIKE_WORMHOLE_DECAY,
    tension_threshold: float = SPIKE_TENSION_THRESHOLD,
    max_neighbors: int = SPIKE_MAX_NEIGHBORS_PER_NODE,
    max_emergent: int = SPIKE_MAX_EMERGENT_NODES,
) -> SpikeResult:
    """V6 LIF spike propagation along a directed cooccurrence matrix.

    Mirrors `TagMemoEngine.applyTagBoost` § [4.5] (TagMemoEngine.js:186-263):
    - Each seed fires with `adjustedWeight` energy and `base_momentum` TTL.
    - On each hop, every active spike injects current into its top-K neighbours.
    - Edges with `coocWeight * residual >= tension_threshold` are "wormholes":
      they decay at `wormhole_decay` (vs `base_decay`) and cost no momentum.
    - Hardcoded gates: skip injection below `_INJECTED_CURRENT_MIN`, skip neighbour
      after momentum drops < 0 unless wormhole, declare hop productive only if
      any pulse exceeds `_PROPAGATION_PULSE_MIN`.
    - Returns the accumulated energy field (seeds + emergent), plus cap diagnostics.
    """
    residuals_map = residuals or {}
    seeds = {int(tag_id): float(weight) for tag_id, weight in seed_weights.items() if float(weight) > 0.0}
    seed_ids = frozenset(seeds)

    if not seeds or matrix.edge_count == 0:
        return SpikeResult(
            accumulated_energy=dict(seeds),
            seed_count=len(seeds),
            emergent_count=0,
            hops_executed=0,
            truncated_by_cap=False,
            seed_ids=seed_ids,
        )

    # Initial injection
    active: dict[int, tuple[float, float]] = {tid: (energy, base_momentum) for tid, energy in seeds.items()}
    accumulated: dict[int, float] = dict(seeds)

    productive_hops = 0
    neighbor_cap_hit = False

    for _ in range(max_hops):
        next_spikes: dict[int, tuple[float, float]] = {}
        propagated = False

        for node_id, (energy, momentum) in active.items():
            if energy < firing_threshold or momentum < 0:
                continue
            synapses = matrix.neighbors(node_id)
            if not synapses:
                continue
            if len(synapses) > max_neighbors:
                neighbor_cap_hit = True
            sorted_synapses = sorted(synapses.items(), key=lambda kv: (-float(kv[1]), int(kv[0])))[:max_neighbors]

            for neighbor_id, cooc_weight in sorted_synapses:
                cooc_weight_f = float(cooc_weight)
                neighbor_residual = float(residuals_map.get(int(neighbor_id), 1.0))
                tension = cooc_weight_f * neighbor_residual
                is_wormhole = tension >= tension_threshold

                decay_factor = wormhole_decay if is_wormhole else base_decay
                momentum_cost = 0.0 if is_wormhole else 1.0

                injected = energy * cooc_weight_f * decay_factor
                if injected < _INJECTED_CURRENT_MIN:
                    continue

                next_momentum = momentum - momentum_cost
                if next_momentum < 0 and not is_wormhole:
                    continue

                existing = next_spikes.get(int(neighbor_id))
                if existing is not None:
                    next_spikes[int(neighbor_id)] = (
                        existing[0] + injected,
                        max(existing[1], next_momentum),
                    )
                else:
                    next_spikes[int(neighbor_id)] = (injected, next_momentum)

        for nid, (new_energy, _new_momentum) in next_spikes.items():
            accumulated[nid] = accumulated.get(nid, 0.0) + new_energy
            if new_energy > _PROPAGATION_PULSE_MIN:
                propagated = True

        if not propagated:
            break
        productive_hops += 1
        active = next_spikes

    emergent_count = sum(1 for tid in accumulated if tid not in seed_ids)
    truncated_by_cap = bool(
        neighbor_cap_hit
        or productive_hops >= max_hops
        or emergent_count > max_emergent
    )

    return SpikeResult(
        accumulated_energy=accumulated,
        seed_count=len(seeds),
        emergent_count=emergent_count,
        hops_executed=productive_hops,
        truncated_by_cap=truncated_by_cap,
        seed_ids=seed_ids,
    )


# ---------------------------------------------------------------------------
# apply_tag_boost: full Phase 1 query-vector enhancement pipeline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TagBoostInfo:
    seed_tag_ids: tuple[int, ...] = ()
    seed_count: int = 0
    emergent_count: int = 0
    matched_tag_names: tuple[str, ...] = ()
    boost_factor_applied: float = 0.0
    matrix_loaded: bool = False
    skipped_reason: str = ""
    truncated_by_cap: bool = False

    def to_dict(self) -> dict:
        return {
            "seed_tag_ids": list(self.seed_tag_ids),
            "seed_count": int(self.seed_count),
            "emergent_count": int(self.emergent_count),
            "matched_tag_names": list(self.matched_tag_names),
            "boost_factor_applied": float(self.boost_factor_applied),
            "matrix_loaded": bool(self.matrix_loaded),
            "skipped_reason": str(self.skipped_reason),
            "truncated_by_cap": bool(self.truncated_by_cap),
        }


@dataclass(frozen=True)
class _TagVecRow:
    tag_id: int
    name: str
    vector: np.ndarray


_MATRIX_CACHE_LOCK = threading.Lock()
_MATRIX_CACHE_MAX = 16
_MATRIX_CACHE: "dict[tuple[str, int], CooccurrenceMatrix | None]" = {}


def _load_matrix_cached(path: Path, kb_name: str) -> CooccurrenceMatrix | None:
    if not path.exists():
        return None
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return None
    key = (str(path), mtime_ns)
    with _MATRIX_CACHE_LOCK:
        if key in _MATRIX_CACHE:
            return _MATRIX_CACHE[key]
    matrix = load_cooccurrence(path)
    with _MATRIX_CACHE_LOCK:
        if len(_MATRIX_CACHE) >= _MATRIX_CACHE_MAX:
            # FIFO eviction; rebuild creates new mtime so stale entries naturally retire
            try:
                _MATRIX_CACHE.pop(next(iter(_MATRIX_CACHE)))
            except StopIteration:
                pass
        _MATRIX_CACHE[key] = matrix
    return matrix


def _reset_matrix_cache_for_tests() -> None:
    with _MATRIX_CACHE_LOCK:
        _MATRIX_CACHE.clear()


def _phase0_registry_path(cfg: Settings):
    if cfg.manual_library.registry_path == "data/manual_registry.sqlite3":
        return Path(cfg.storage.data_dir) / "manual_registry.sqlite3"
    return cfg.manual_library.registry_path


def _load_kb_tag_vectors(cfg: Settings, kb_name: str, expected_dim: int) -> list[_TagVecRow]:
    registry = create_registry(_phase0_registry_path(cfg))
    rows: list[_TagVecRow] = []
    with registry.connection() as conn:
        for tag in iter_canonical_tags_with_vectors(conn, kb_name=kb_name):
            if tag.vector is None or tag.embedding_dim != expected_dim:
                continue
            vector = np.frombuffer(tag.vector, dtype=np.float32)
            if vector.shape != (expected_dim,):
                continue
            rows.append(_TagVecRow(tag_id=tag.id, name=tag.name, vector=np.asarray(vector, dtype=np.float32)))
    return rows


def _select_seeds(
    query_vec: np.ndarray,
    tag_rows: list[_TagVecRow],
    *,
    top_k: int,
    min_similarity: float,
) -> list[tuple[_TagVecRow, float]]:
    if not tag_rows:
        return []
    q = np.asarray(query_vec, dtype=np.float32)
    q_norm = float(np.linalg.norm(q))
    if q_norm < 1e-9:
        return []
    sims: list[tuple[_TagVecRow, float]] = []
    for row in tag_rows:
        v_norm = float(np.linalg.norm(row.vector))
        if v_norm < 1e-9:
            continue
        sim = float(np.dot(q, row.vector) / (q_norm * v_norm))
        if sim >= min_similarity:
            sims.append((row, sim))
    sims.sort(key=lambda kv: (-kv[1], kv[0].tag_id))
    return sims[:top_k]


def _semantic_dedup(
    candidates: list[tuple[_TagVecRow, float]],
    *,
    threshold: float,
    weight_transfer: float,
) -> list[tuple[_TagVecRow, float]]:
    """Cosine > threshold ⇒ merge weight into earlier representative (matches source [5.5])."""
    if not candidates:
        return []
    sorted_cands = sorted(candidates, key=lambda kv: (-kv[1], kv[0].tag_id))
    kept: list[list] = []  # mutable [row, weight]
    for row, weight in sorted_cands:
        merged = False
        for entry in kept:
            existing_row: _TagVecRow = entry[0]
            cos = _cosine(existing_row.vector, row.vector)
            if cos > threshold:
                entry[1] = float(entry[1]) + float(weight) * float(weight_transfer)
                merged = True
                break
        if not merged:
            kept.append([row, float(weight)])
    return [(entry[0], float(entry[1])) for entry in kept]


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _weighted_context(candidates: list[tuple[_TagVecRow, float]], dim: int) -> np.ndarray | None:
    if not candidates:
        return None
    total_weight = sum(max(float(weight), 0.0) for _row, weight in candidates)
    if total_weight <= 0.0:
        return None
    accum = np.zeros(dim, dtype=np.float32)
    for row, weight in candidates:
        if float(weight) <= 0.0:
            continue
        accum += np.asarray(row.vector, dtype=np.float32) * (float(weight) / total_weight)
    norm = float(np.linalg.norm(accum))
    if norm < 1e-9:
        return None
    return accum / norm


def _resolve_dynamic_boost(query_vec: np.ndarray, settings: Settings) -> float:
    """Resolve dynamic_boost_factor.

    "constant" (default per D2): always 1.0 — visible spike under cold-start EPA.
    "epa": ``max(epa_floor, logicDepth * epa_logic_depth_scale)``. Falls back to
           constant if the projector cannot be loaded (defensive — never crash
           search). Class defaults (scale=1.0, floor=0.0) are equivalent to
           Phase 1's raw logicDepth pass-through; config.yaml may tune scale.
    """
    strategy = settings.wave_phase1.dynamic_boost_factor_strategy
    if strategy == "constant":
        return 1.0
    if strategy == "epa":
        try:
            from .epa_basis import basis_path
            from .epa_projector import EPAProjector
        except Exception:
            return 1.0
        try:
            projector = EPAProjector.from_path(basis_path(settings))
        except Exception:
            return 1.0
        try:
            projection = projector.project(np.asarray(query_vec, dtype=np.float32))
        except Exception:
            return 1.0
        logic_depth = max(0.0, float(projection.get("logicDepth", 0.0)))
        scale = float(settings.wave_phase1.epa_logic_depth_scale)
        floor = float(settings.wave_phase1.epa_floor)
        return max(floor, logic_depth * scale)
    return 1.0


def apply_tag_boost(
    query_vec: np.ndarray,
    *,
    kb_name: str,
    settings: Settings,
    base_tag_boost: float,
) -> tuple[np.ndarray, TagBoostInfo]:
    """Apply Phase 1 query-vector enhancement.

    Returns `(boosted_vec, info)`. When the boost cannot be applied (kill switch off,
    matrix missing, no seeds, degenerate context, etc.), returns `(query_vec, info)`
    with `skipped_reason` set so the caller can log structured telemetry.
    """
    cfg = settings.wave_phase1
    if not cfg.enabled or not cfg.spike_enabled:
        return query_vec, TagBoostInfo(skipped_reason="spike_disabled")

    matrix_path = cooccurrence_path(settings, kb_name)
    matrix = _load_matrix_cached(matrix_path, kb_name)
    if matrix is None or matrix.edge_count == 0:
        return query_vec, TagBoostInfo(skipped_reason="matrix_missing")

    expected_dim = int(np.asarray(query_vec).shape[0])
    tag_rows = _load_kb_tag_vectors(settings, kb_name, expected_dim)
    if not tag_rows:
        return query_vec, TagBoostInfo(skipped_reason="no_tag_vectors", matrix_loaded=True)

    seeds_with_sim = _select_seeds(
        query_vec,
        tag_rows,
        top_k=cfg.seed_top_k,
        min_similarity=cfg.seed_min_similarity,
    )
    if not seeds_with_sim:
        return query_vec, TagBoostInfo(skipped_reason="no_seeds", matrix_loaded=True)

    seed_weights = {row.tag_id: float(sim) for row, sim in seeds_with_sim}
    spike_result = propagate(
        seed_weights,
        matrix,
        max_hops=cfg.spike_max_hops,
        base_momentum=cfg.spike_base_momentum,
        firing_threshold=cfg.spike_firing_threshold,
        base_decay=cfg.spike_base_decay,
        wormhole_decay=cfg.spike_wormhole_decay,
        tension_threshold=cfg.spike_tension_threshold,
        max_neighbors=cfg.spike_max_neighbors_per_node,
        max_emergent=cfg.spike_max_emergent_nodes,
    )

    # Merge seeds + emergent. Seeds keep max(seed_weight, propagated); emergent
    # keep accumulated_energy. Cap emergent at max_emergent (sorted by weight).
    rows_by_id = {row.tag_id: row for row in tag_rows}
    merged: dict[int, float] = {}
    seed_ids = spike_result.seed_ids
    for tag_id, energy in spike_result.accumulated_energy.items():
        if tag_id in seed_ids:
            merged[tag_id] = max(seed_weights.get(tag_id, 0.0), float(energy))
        else:
            if tag_id in rows_by_id:  # only consume tags whose vectors we have
                merged[tag_id] = float(energy)

    seed_entries = [(rows_by_id[tid], merged[tid]) for tid in seed_ids if tid in rows_by_id and tid in merged]
    emergent_entries = [
        (rows_by_id[tid], merged[tid])
        for tid in merged
        if tid not in seed_ids and tid in rows_by_id
    ]
    emergent_entries.sort(key=lambda kv: (-kv[1], kv[0].tag_id))
    emergent_entries = emergent_entries[: cfg.spike_max_emergent_nodes]

    candidates = seed_entries + emergent_entries
    if not candidates:
        return query_vec, TagBoostInfo(skipped_reason="no_candidates", matrix_loaded=True)

    deduped = _semantic_dedup(
        candidates,
        threshold=cfg.dedup_threshold,
        weight_transfer=cfg.dedup_weight_transfer,
    )

    context = _weighted_context(deduped, dim=expected_dim)
    if context is None:
        return query_vec, TagBoostInfo(
            skipped_reason="degenerate_context",
            matrix_loaded=True,
            seed_count=len(seed_entries),
            emergent_count=len(emergent_entries),
        )

    dynamic = _resolve_dynamic_boost(query_vec, settings)
    dynamic = float(np.clip(dynamic, cfg.dynamic_boost_min, cfg.dynamic_boost_max))
    effective_boost = float(base_tag_boost) * dynamic
    alpha = float(min(1.0, max(0.0, effective_boost)))
    if alpha <= 0.0:
        return query_vec, TagBoostInfo(
            skipped_reason="zero_alpha",
            matrix_loaded=True,
            seed_count=len(seed_entries),
            emergent_count=len(emergent_entries),
            boost_factor_applied=0.0,
        )

    fused = (1.0 - alpha) * np.asarray(query_vec, dtype=np.float32) + alpha * context
    fused_norm = float(np.linalg.norm(fused))
    if fused_norm < 1e-9:
        return query_vec, TagBoostInfo(
            skipped_reason="degenerate_fused",
            matrix_loaded=True,
            seed_count=len(seed_entries),
            emergent_count=len(emergent_entries),
        )
    fused = fused / fused_norm

    matched_names = tuple(row.name for row, _w in deduped)
    info = TagBoostInfo(
        seed_tag_ids=tuple(sorted(seed_ids)),
        seed_count=len(seed_entries),
        emergent_count=len(emergent_entries),
        matched_tag_names=matched_names,
        boost_factor_applied=alpha,
        matrix_loaded=True,
        truncated_by_cap=spike_result.truncated_by_cap,
    )
    return fused.astype(np.float32), info
