from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
import re
import threading
from typing import Mapping, Sequence

import numpy as np

from .config import Settings
from .manual_registry import create_registry
from .observability.metrics import get_metrics
from .residual_pyramid import (
    PyramidFeatures,
    PyramidResult,
    ResidualPyramid,
)
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
    # Phase 2b-2 fields. Defaults preserve Phase 2b-1 to_dict layout for callers
    # that only read existing fields.
    core_tags_input: tuple[str, ...] = ()
    core_tags_resolved: tuple[str, ...] = ()
    core_completion_count: int = 0
    ghosts_injected: int = 0
    ghost_skipped_dim_mismatch: int = 0
    lang_penalty_applied_count: int = 0
    query_world: str = ""
    # Phase 3: V6 detectCrossDomainResonance contribution to dynamicBoostFactor.
    # Both default 0 ⇒ Phase 2b-2 to_dict layout extends without breaking callers.
    cross_domain_resonance: float = 0.0
    cross_domain_bridges_count: int = 0
    # Phase 3 debug-only: full bridge list (from/to/strength/balance) is exposed
    # to `search_debug_payload` but kept off `to_dict` to avoid bloating the
    # default tag_boost shape. Use the leading underscore to mark private.
    _cross_domain_bridges: tuple[dict, ...] = field(default=(), repr=False, compare=False)

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
            "core_tags_input": list(self.core_tags_input),
            "core_tags_resolved": list(self.core_tags_resolved),
            "core_completion_count": int(self.core_completion_count),
            "ghosts_injected": int(self.ghosts_injected),
            "ghost_skipped_dim_mismatch": int(self.ghost_skipped_dim_mismatch),
            "lang_penalty_applied_count": int(self.lang_penalty_applied_count),
            "query_world": str(self.query_world),
            "cross_domain_resonance": float(self.cross_domain_resonance),
            "cross_domain_bridges_count": int(self.cross_domain_bridges_count),
        }


@dataclass(frozen=True)
class _TagVecRow:
    tag_id: int
    name: str
    vector: np.ndarray


@dataclass(frozen=True)
class GhostTag:
    """Caller-supplied tag with explicit vector, bypassing the KB tag store.

    Source: TagMemoEngine.js:344-372 (V6 ghost injection).
    Negative ids are assigned at injection time so they don't collide with KB tag ids.
    """

    name: str
    vector: np.ndarray
    is_core: bool = False


@dataclass(frozen=True)
class _ResolvedCoreSet:
    """Synonym-resolved + dedup'd core tag canonical names (Phase 2b-2)."""

    input_raw: tuple[str, ...]
    canonical: tuple[str, ...]


# Phase 2b-2: language-penalty + technical-noise pattern matchers.
# Source: TagMemoEngine.js:155-180 (V6 langPenalty regex).
_TECH_TAG_PATTERN = re.compile(r"^[A-Za-z0-9\-_.\s]+$")
_TECH_WORLD_PATTERN = re.compile(r"^[A-Za-z0-9\-_.]+$")
_SOCIAL_WORLD_PATTERN = re.compile(r"Politics|Society|History|Economics|Culture", re.IGNORECASE)
_CJK_PATTERN = re.compile(r"[一-龥]")


# Lazy policy cache for synonym resolution. Key = (kb_name, id(settings)) so
# different test fixtures don't collide. Cleared via _reset_matrix_cache_for_tests.
_TAG_POLICY_CACHE_LOCK = threading.Lock()
_TAG_POLICY_CACHE: "dict[tuple[str, int], object]" = {}


def _load_tag_policy_cached(kb_name: str, settings: Settings) -> object | None:
    """Lazy-load tag governance policy for a KB; cached per (kb_name, settings)."""
    key = (kb_name, id(settings))
    with _TAG_POLICY_CACHE_LOCK:
        if key in _TAG_POLICY_CACHE:
            return _TAG_POLICY_CACHE[key]
    try:
        from .tag_governance import load_tag_policy

        policy = load_tag_policy(kb_name, settings)
    except Exception:
        policy = None
    with _TAG_POLICY_CACHE_LOCK:
        _TAG_POLICY_CACHE[key] = policy
    return policy


def _resolve_canonical_via_governance(kb_name: str, raw_tag: str, settings: Settings) -> str:
    """Map a raw tag to its canonical name via tag_governance synonym table.

    Returns the lowercase raw input on any failure (defensive — synonym resolve
    must never break search). Source: tag_governance.resolve_tag.
    """
    policy = _load_tag_policy_cached(kb_name, settings)
    if policy is None:
        return raw_tag
    try:
        from .tag_governance import resolve_tag

        resolution = resolve_tag(raw_tag, policy)
        target = (resolution.canonical_tag or resolution.tag or raw_tag).strip().lower()
        return target or raw_tag
    except Exception:
        return raw_tag


def _resolve_core_tag_set(
    raw: Sequence[str], *, kb_name: str, settings: Settings
) -> _ResolvedCoreSet:
    """Synonym-resolve + dedup caller-supplied core_tags.

    - Strips whitespace, lowercases, drops empty / non-string entries.
    - For each cleaned input, asks tag_governance to map to canonical.
    - Returns frozen tuples for input_raw (post-clean) and canonical.
    """
    cleaned: list[str] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, str):
            continue
        s = entry.strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        cleaned.append(s)

    canonical: list[str] = []
    canonical_seen: set[str] = set()
    for raw_lower in cleaned:
        target = _resolve_canonical_via_governance(kb_name, raw_lower, settings)
        target = (target or raw_lower).strip().lower()
        if not target or target in canonical_seen:
            continue
        canonical_seen.add(target)
        canonical.append(target)
    return _ResolvedCoreSet(input_raw=tuple(cleaned), canonical=tuple(canonical))


def _resolve_core_boost_factor(
    query_vec: np.ndarray,
    settings: Settings,
    *,
    pyramid_features: PyramidFeatures | None = None,
) -> float:
    """Compute dynamicCoreBoostFactor in the configured [core_boost_min, core_boost_max] range.

    Source: TagMemoEngine.js:96-98.
        coreMetric = 0.5 * logicDepth + 0.5 * (1 - coverage)
        factor = core_boost_min + clamp(coreMetric, 0, 1) * (core_boost_max - core_boost_min)

    `logicDepth` comes from the EPA projector; `coverage` from pyramid features
    (0.0 when pyramid is disabled / unavailable). On any EPA failure we treat
    logicDepth=0 ⇒ factor approaches core_boost_min (~1.20), the conservative end.
    """
    cfg = settings.wave_phase1
    logic_depth = 0.0
    try:
        from .epa_basis import basis_path
        from .epa_projector import EPAProjector

        projector = EPAProjector.from_path(basis_path(settings))
        projection = projector.project(np.asarray(query_vec, dtype=np.float32))
        logic_depth = max(0.0, float(projection.get("logicDepth", 0.0)))
    except Exception:
        logic_depth = 0.0
    coverage = 0.0
    if pyramid_features is not None:
        coverage = max(0.0, min(1.0, float(pyramid_features.coverage)))
    core_metric = 0.5 * logic_depth + 0.5 * (1.0 - coverage)
    core_metric = max(0.0, min(1.0, core_metric))
    cmin = float(cfg.core_boost_min)
    cmax = float(cfg.core_boost_max)
    return cmin + core_metric * (cmax - cmin)


def _per_tag_core_boost(
    is_core: bool,
    individual_relevance: float,
    dynamic_core: float,
) -> float:
    """Multiplicative boost applied to a single core-tag candidate's weight.

    Source: TagMemoEngine.js:144-145.
        coreBoost = dynamicCoreBoostFactor * (0.95 + clamp(individualRelevance, 0, 1) * 0.10)
    Non-core tags pass through (1.0).
    """
    if not is_core:
        return 1.0
    rel = max(0.0, min(1.0, float(individual_relevance)))
    return float(dynamic_core) * (0.95 + rel * 0.10)


def _compute_lang_penalty(
    tag_name: str,
    query_world: str,
    settings: Settings,
) -> tuple[float, str]:
    """Decide whether a candidate tag is "technical noise" relative to the query world.

    Returns (penalty_multiplier, query_world_kind). Kinds:
      - "disabled"          — feature flag off (always 1.0)
      - "technical"         — query world looks technical, no penalty (1.0)
      - "unknown"           — query world unset/Unknown, tag is technical noise ⇒ penalty_unknown
      - "social"            — query world matches Politics|Society|... ⇒ sqrt(penalty_cross_domain)
      - "cross_domain_other"— query world non-technical non-social, tag is technical noise ⇒ penalty_cross_domain

    Source: TagMemoEngine.js:155-180.
    Tag name with any CJK character is never penalized (it's a real human-language tag).
    Tag name must be > 3 chars to count as technical noise (avoids penalizing short codes).
    """
    cfg = settings.wave_phase1
    if not cfg.lang_penalty_enabled:
        return 1.0, "disabled"
    name = tag_name or ""
    has_cjk = bool(_CJK_PATTERN.search(name))
    is_tech_noise = (
        not has_cjk
        and bool(_TECH_TAG_PATTERN.match(name))
        and len(name) > 3
    )
    qw = (query_world or "").strip()
    if qw and qw != "Unknown" and bool(_TECH_WORLD_PATTERN.match(qw)):
        return 1.0, "technical"
    if not is_tech_noise:
        # Tag isn't technical noise (CJK, too short, or has special chars) ⇒ no penalty.
        kind = "unknown" if (not qw or qw == "Unknown") else "cross_domain_other"
        return 1.0, kind
    if not qw or qw == "Unknown":
        return float(cfg.lang_penalty_unknown), "unknown"
    base = float(cfg.lang_penalty_cross_domain)
    if _SOCIAL_WORLD_PATTERN.search(qw):
        return math.sqrt(base), "social"
    return base, "cross_domain_other"


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
    with _TAG_POLICY_CACHE_LOCK:
        _TAG_POLICY_CACHE.clear()


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


def _load_kb_tag_vectors_by_names(
    cfg: Settings,
    kb_name: str,
    names: Sequence[str],
    expected_dim: int,
) -> list[_TagVecRow]:
    """Load specific KB tag rows by name (case-insensitive), filtered to expected dim.

    Returns rows in the order of `names` (after dedup), skipping any name not present
    in DB or with mismatched embedding dim. Used by `_inject_core_completion`.
    """
    if not names:
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for n in names:
        s = (n or "").strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        ordered.append(s)
    if not ordered:
        return []
    placeholders = ",".join("?" for _ in ordered)
    sql = (
        "SELECT id, name, vector, embedding_dim FROM tags "
        f"WHERE kb_name=? AND lower(name) IN ({placeholders})"
    )
    params = [kb_name, *ordered]
    rows_by_name: dict[str, _TagVecRow] = {}
    try:
        registry = create_registry(_phase0_registry_path(cfg))
        with registry.connection() as conn:
            cursor = conn.execute(sql, params)
            for row in cursor.fetchall():
                vec_bytes = row["vector"]
                dim = row["embedding_dim"]
                if vec_bytes is None or int(dim) != int(expected_dim):
                    continue
                vector = np.frombuffer(vec_bytes, dtype=np.float32)
                if vector.shape != (expected_dim,):
                    continue
                lower = str(row["name"]).strip().lower()
                rows_by_name[lower] = _TagVecRow(
                    tag_id=int(row["id"]),
                    name=str(row["name"]),
                    vector=np.asarray(vector, dtype=np.float32),
                )
    except Exception:
        # SQL/IO failure must not break search — return whatever we collected.
        pass
    return [rows_by_name[n] for n in ordered if n in rows_by_name]


def _inject_core_completion(
    *,
    existing: list[tuple[_TagVecRow, float, bool]],
    canonical_core: Sequence[str],
    kb_name: str,
    settings: Settings,
    expected_dim: int,
    dynamic_core: float,
) -> tuple[list[tuple[_TagVecRow, float, bool]], int]:
    """Pull missing core tags from KB and inject with maxBaseWeight × dynamic_core.

    Source: TagMemoEngine.js:312-342. Returns (extended_list, count_added).

    `maxBaseWeight = max(weight / dynamic_core)` over existing candidates so the
    injected core tags sit at the same magnitude as the strongest natural candidate.
    Empty `existing` ⇒ `maxBaseWeight = 1.0`.
    """
    if not canonical_core:
        return existing, 0
    seen_lower: set[str] = {row.name.strip().lower() for row, _w, _c in existing}
    missing = [c for c in canonical_core if c not in seen_lower]
    if not missing:
        return existing, 0
    if existing and dynamic_core > 1e-9:
        max_base = max(float(w) / float(dynamic_core) for _r, w, _c in existing)
    elif existing:
        max_base = max(float(w) for _r, w, _c in existing)
    else:
        max_base = 1.0
    rows = _load_kb_tag_vectors_by_names(settings, kb_name, missing, expected_dim)
    out = list(existing)
    added = 0
    for row in rows:
        lower = row.name.strip().lower()
        if lower in seen_lower:
            continue
        seen_lower.add(lower)
        weight = float(max_base) * float(dynamic_core)
        out.append((row, weight, True))
        added += 1
    return out, added


def _inject_ghosts(
    *,
    existing: list[tuple[_TagVecRow, float, bool]],
    ghosts: Sequence[GhostTag],
    expected_dim: int,
    dynamic_core: float,
) -> tuple[list[tuple[_TagVecRow, float, bool]], int, int, int]:
    """Inject caller-supplied ghost tags with negative ids; skip dim mismatches.

    Source: TagMemoEngine.js:344-372. Returns
    ``(extended_list, hard_injected, soft_injected, dim_skipped)``.

    `maxBaseWeight` baseline matches `_inject_core_completion`. Hard ghosts (is_core=True)
    use weight = max_base × dynamic_core; soft ghosts use weight = max_base × 1.0.
    Negative ids decrement from -1, so multiple ghosts never collide with each other
    or with KB tag ids (which are positive). The split between hard / soft / skipped
    is reported separately so callers can label observability metrics correctly even
    when only some hard ghosts pass the dim check.
    """
    if not ghosts:
        return existing, 0, 0, 0
    if existing and dynamic_core > 1e-9:
        max_base = max(float(w) / float(dynamic_core) for _r, w, _c in existing)
    elif existing:
        max_base = max(float(w) for _r, w, _c in existing)
    else:
        max_base = 1.0
    out = list(existing)
    next_id = -1
    hard_injected = 0
    soft_injected = 0
    skipped_dim = 0
    for ghost in ghosts:
        name = (getattr(ghost, "name", "") or "").strip()
        if not name:
            skipped_dim += 1
            continue
        try:
            vec = np.asarray(ghost.vector, dtype=np.float32)
        except Exception:
            skipped_dim += 1
            continue
        if vec.shape != (expected_dim,):
            skipped_dim += 1
            continue
        is_core = bool(getattr(ghost, "is_core", False))
        weight = float(max_base) * (float(dynamic_core) if is_core else 1.0)
        ghost_row = _TagVecRow(tag_id=next_id, name=name, vector=vec)
        next_id -= 1
        out.append((ghost_row, weight, is_core))
        if is_core:
            hard_injected += 1
        else:
            soft_injected += 1
    return out, hard_injected, soft_injected, skipped_dim


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


@dataclass(frozen=True)
class _DynamicBoostResult:
    """Result of `_resolve_dynamic_boost` — dynamic factor + EPA query-world label.

    `query_world` is the dominant EPA axis label (Phase 2b-2 langPenalty input);
    empty string when EPA basis is unavailable or strategy="constant".

    Phase 3: `resonance` is the V6 detectCrossDomainResonance scalar (0 unless
    `wave_phase1.cross_domain_resonance_enabled`), and `bridges` is the matching
    diagnostic list (empty unless enabled and at least one co-activation crosses
    `_RESONANCE_CO_ACTIVATION_THRESHOLD`).
    """

    dynamic: float
    query_world: str
    resonance: float = 0.0
    bridges: tuple[dict, ...] = ()


# Phase 3: V6 EPAModule.js:186 hardcoded co-activation threshold. Source does not
# expose this to config; we mirror that decision (PRD D6).
_RESONANCE_CO_ACTIVATION_THRESHOLD = 0.15


def detect_cross_domain_resonance(
    dominant_axes: Sequence[Mapping[str, object]],
) -> tuple[float, list[dict]]:
    """V6 detectCrossDomainResonance port.

    Source: lioensky/VCPToolBox EPAModule.js:170-201 (commit aff66193). For each
    secondary axis paired with the top axis, compute geometric-mean co-activation
    ``sqrt(top.energy * sec.energy)``; entries strictly above
    `_RESONANCE_CO_ACTIVATION_THRESHOLD` form a "bridge". Total resonance is the
    sum of bridge strengths and feeds dynamicBoostFactor as ``log(1 + resonance)``.

    Args:
        dominant_axes: items shaped like ``{"label": str, "energy": float, ...}``
            (output of `EPAProjector.project()["dominantAxes"]`). Both Mapping
            instances and dataclass-like objects with ``.get()`` are accepted —
            the helper falls back to ``getattr`` to stay compatible with future
            shapes.

    Returns:
        ``(resonance_total, bridges)`` where ``bridges`` is a list of
        ``{"from", "to", "strength", "balance"}`` dicts (diagnostics only).
    """
    if len(dominant_axes) < 2:
        return 0.0, []

    def _read(axis: object, key: str, default: object) -> object:
        getter = getattr(axis, "get", None)
        if callable(getter):
            return getter(key, default)
        return getattr(axis, key, default)

    top = dominant_axes[0]
    top_energy = float(_read(top, "energy", 0.0))
    top_label = str(_read(top, "label", "") or "")
    bridges: list[dict] = []
    for sec in dominant_axes[1:]:
        sec_energy = float(_read(sec, "energy", 0.0))
        co_act = math.sqrt(max(0.0, top_energy * sec_energy))
        if co_act > _RESONANCE_CO_ACTIVATION_THRESHOLD:
            sec_label = str(_read(sec, "label", "") or "")
            top_e = max(0.0, top_energy)
            sec_e = max(0.0, sec_energy)
            denom = max(top_e, sec_e)
            balance = (min(top_e, sec_e) / denom) if denom > 1e-12 else 0.0
            bridges.append(
                {
                    "from": top_label,
                    "to": sec_label,
                    "strength": co_act,
                    "balance": balance,
                }
            )
    resonance_total = sum(float(b["strength"]) for b in bridges)
    return resonance_total, bridges


def _resolve_dynamic_boost(
    query_vec: np.ndarray,
    settings: Settings,
    *,
    pyramid_features: PyramidFeatures | None = None,
) -> float:
    """Backward-compatible wrapper returning only the dynamic factor.

    Internal callers that also need the EPA `query_world` should call
    `_resolve_dynamic_boost_with_world`. See that function's docstring for the
    full strategy semantics.
    """
    return _resolve_dynamic_boost_with_world(
        query_vec, settings, pyramid_features=pyramid_features
    ).dynamic


def _resolve_dynamic_boost_with_world(
    query_vec: np.ndarray,
    settings: Settings,
    *,
    pyramid_features: PyramidFeatures | None = None,
) -> _DynamicBoostResult:
    """Resolve dynamic_boost_factor + EPA query world (Phase 2b-2).

    "constant" (default per D2): always 1.0 — visible spike under cold-start EPA.
    "epa" (Phase 2a): ``max(epa_floor, logicDepth * epa_logic_depth_scale)``.
    "pyramid" (Phase 2b-1): full source formula
        ``(logicDepth * (1+log(1+resonance)) / (1+entropy*0.5)) * activation_mult``,
        then post-multiplied by ``epa_logic_depth_scale`` and floored at
        ``epa_floor`` (D4 escape hatch). ``activation_mult`` is derived from
        ``pyramid_features.tag_memo_activation``; ``resonance`` is stubbed to 0
        (Phase 0/1/2a/2b-1 do not implement detectCrossDomainResonance).
    Falls back to constant if the projector cannot be loaded (defensive — never
    crash search). `query_world` is "" on the constant path or any EPA failure.
    """
    cfg = settings.wave_phase1
    strategy = cfg.dynamic_boost_factor_strategy
    if strategy == "constant":
        return _DynamicBoostResult(dynamic=1.0, query_world="")
    if strategy in ("epa", "pyramid"):
        try:
            from .epa_basis import basis_path
            from .epa_projector import EPAProjector
        except Exception:
            return _DynamicBoostResult(dynamic=1.0, query_world="")
        try:
            projector = EPAProjector.from_path(basis_path(settings))
        except Exception:
            return _DynamicBoostResult(dynamic=1.0, query_world="")
        try:
            projection = projector.project(np.asarray(query_vec, dtype=np.float32))
        except Exception:
            return _DynamicBoostResult(dynamic=1.0, query_world="")
        logic_depth = max(0.0, float(projection.get("logicDepth", 0.0)))
        scale = float(cfg.epa_logic_depth_scale)
        floor = float(cfg.epa_floor)
        # Source TagMemoEngine.js:73 — queryWorld = dominantAxes[0].label || 'Unknown'.
        dominant = projection.get("dominantAxes") or []
        query_world = ""
        if dominant:
            label = dominant[0]
            if isinstance(label, dict):
                query_world = str(label.get("label") or "")
            else:
                query_world = str(getattr(label, "label", "") or "")
        if not query_world:
            query_world = "Unknown"

        if strategy == "epa":
            return _DynamicBoostResult(
                dynamic=max(floor, logic_depth * scale),
                query_world=query_world,
            )

        # strategy == "pyramid"
        entropy = max(0.0, min(1.0, float(projection.get("entropy", 0.0))))
        # Phase 3: replace `resonance = 0` stub with V6 detectCrossDomainResonance
        # when explicitly enabled. Default off keeps the formula numerically
        # equivalent to Phase 2b-1 (log(1+0) = 0 ⇒ resonance term = 1.0).
        resonance = 0.0
        bridges: list[dict] = []
        if cfg.cross_domain_resonance_enabled:
            resonance, bridges = detect_cross_domain_resonance(dominant)
        if pyramid_features is None:
            tag_memo_activation = 0.0  # pyramid empty / disabled fallback
        else:
            tag_memo_activation = max(0.0, min(1.0, float(pyramid_features.tag_memo_activation)))
        act_min = float(cfg.activation_multiplier_min)
        act_max = float(cfg.activation_multiplier_max)
        activation_mult = act_min + tag_memo_activation * (act_max - act_min)
        resonance_term = math.log(1.0 + max(0.0, resonance))
        dynamic = (
            (logic_depth * (1.0 + resonance_term) / (1.0 + entropy * 0.5)) * activation_mult
        )
        # D8: post-scale calibrated for hashing dim=64 fixture (default 4.0); D4 floor.
        post_scale = float(cfg.pyramid_post_scale)
        return _DynamicBoostResult(
            dynamic=max(floor, dynamic * post_scale),
            query_world=query_world,
            resonance=float(resonance),
            bridges=tuple(bridges),
        )
    return _DynamicBoostResult(dynamic=1.0, query_world="")


def apply_tag_boost(
    query_vec: np.ndarray,
    *,
    kb_name: str,
    settings: Settings,
    base_tag_boost: float,
    core_tags: Sequence[str] = (),
    ghost_tags: Sequence[GhostTag] = (),
) -> tuple[np.ndarray, TagBoostInfo]:
    """Apply Phase 1 query-vector enhancement.

    Returns `(boosted_vec, info)`. When the boost cannot be applied (kill switch off,
    matrix missing, no seeds, degenerate context, etc.), returns `(query_vec, info)`
    with `skipped_reason` set so the caller can log structured telemetry.

    Phase 2b-2: `core_tags` and `ghost_tags` are caller-supplied "spotlight" hints.
    They are resolved + recorded for diagnostics on every code path, but only
    influence weights under `strategy="pyramid"` (PRD R10). For other strategies
    they round-trip through `info` unchanged.
    """
    cfg = settings.wave_phase1
    # Phase 2b-2: resolve core_tags up front so every early-return TagBoostInfo
    # can record what the caller asked for. resolve_core never raises.
    resolved_core = _resolve_core_tag_set(core_tags, kb_name=kb_name, settings=settings)
    base_info_kwargs: dict = {
        "core_tags_input": resolved_core.input_raw,
        "core_tags_resolved": resolved_core.canonical,
    }

    if not cfg.enabled or not cfg.spike_enabled:
        return query_vec, TagBoostInfo(skipped_reason="spike_disabled", **base_info_kwargs)

    matrix_path = cooccurrence_path(settings, kb_name)
    matrix = _load_matrix_cached(matrix_path, kb_name)
    if matrix is None or matrix.edge_count == 0:
        return query_vec, TagBoostInfo(skipped_reason="matrix_missing", **base_info_kwargs)

    expected_dim = int(np.asarray(query_vec).shape[0])
    tag_rows = _load_kb_tag_vectors(settings, kb_name, expected_dim)
    if not tag_rows:
        return query_vec, TagBoostInfo(
            skipped_reason="no_tag_vectors", matrix_loaded=True, **base_info_kwargs
        )

    # Phase 2b-1: strategy="pyramid" replaces top-K cosine seed selection with
    # multi-level Gram-Schmidt energy decomposition. ResidualPyramid is a pure
    # algorithm; on any failure we fall back to the cosine path so search never
    # crashes (PRD R4 / D5).
    pyramid_result: PyramidResult | None = None
    if cfg.dynamic_boost_factor_strategy == "pyramid":
        try:
            pyramid = ResidualPyramid(
                tag_rows,
                dim=expected_dim,
                max_levels=cfg.pyramid_max_levels,
                top_k=cfg.pyramid_top_k,
                min_energy_ratio=cfg.pyramid_min_energy_ratio,
                use_handshake_features=cfg.pyramid_use_handshake_features,
            )
            pyramid_result = pyramid.analyze(query_vec)
        except Exception:
            pyramid_result = None

    # Phase 2b-2: resolve EPA query world up front (used both by the pyramid
    # candidate-collection langPenalty pass and as the dynamic-boost output).
    boost_with_world = _resolve_dynamic_boost_with_world(
        query_vec,
        settings,
        pyramid_features=pyramid_result.features if pyramid_result is not None else None,
    )
    query_world = boost_with_world.query_world

    # `is_core` is computed when collecting candidates so that downstream passes
    # (core completion / ghost injection) and TagBoostInfo can preserve it.
    seeds_with_sim: list[tuple[_TagVecRow, float]]
    candidates_triple_initial: list[tuple[_TagVecRow, float, bool]] = []
    lang_applied_by_kind: dict[str, int] = {}
    use_pyramid_path = pyramid_result is not None and pyramid_result.levels
    if use_pyramid_path:
        rows_by_id_seed = {row.tag_id: row for row in tag_rows}
        layer_decay_base = float(cfg.pyramid_layer_decay_base)
        core_canonical_set = set(resolved_core.canonical)
        dynamic_core_factor = _resolve_core_boost_factor(
            query_vec, settings, pyramid_features=pyramid_result.features
        ) if pyramid_result is not None else 1.0
        seen_tag_ids: set[int] = set()
        for level in pyramid_result.levels:
            decay = layer_decay_base ** int(level.level)
            for ptag in level.tags:
                if ptag.tag_id in seen_tag_ids:
                    continue
                row = rows_by_id_seed.get(ptag.tag_id)
                if row is None:
                    continue
                is_core = row.name.strip().lower() in core_canonical_set
                core_boost = _per_tag_core_boost(
                    is_core, float(ptag.similarity), dynamic_core_factor
                )
                lang_pen, world_kind = _compute_lang_penalty(row.name, query_world, settings)
                if lang_pen < 1.0:
                    lang_applied_by_kind[world_kind] = lang_applied_by_kind.get(world_kind, 0) + 1
                weight = float(ptag.contribution) * decay * lang_pen * core_boost
                if weight <= 0.0:
                    continue
                seen_tag_ids.add(ptag.tag_id)
                candidates_triple_initial.append((row, weight, is_core))
        # Spike still operates on the (id, weight) seed map; carry weights without is_core.
        seeds_with_sim = [(row, weight) for row, weight, _ic in candidates_triple_initial]
    else:
        dynamic_core_factor = 1.0
        seeds_with_sim = _select_seeds(
            query_vec,
            tag_rows,
            top_k=cfg.seed_top_k,
            min_similarity=cfg.seed_min_similarity,
        )
    lang_applied_count = sum(lang_applied_by_kind.values())

    if not seeds_with_sim:
        return query_vec, TagBoostInfo(
            skipped_reason="no_seeds",
            matrix_loaded=True,
            query_world=query_world,
            **base_info_kwargs,
        )

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

    # Reuse is_core flags from pyramid pass when available; non-pyramid path is_core=False.
    is_core_by_id = {row.tag_id: ic for row, _w, ic in candidates_triple_initial}
    seed_entries = [
        (rows_by_id[tid], merged[tid], bool(is_core_by_id.get(tid, False)))
        for tid in seed_ids
        if tid in rows_by_id and tid in merged
    ]
    emergent_entries = [
        (rows_by_id[tid], merged[tid], bool(is_core_by_id.get(tid, False)))
        for tid in merged
        if tid not in seed_ids and tid in rows_by_id
    ]
    emergent_entries.sort(key=lambda kv: (-kv[1], kv[0].tag_id))
    emergent_entries = emergent_entries[: cfg.spike_max_emergent_nodes]

    candidates_triple = seed_entries + emergent_entries
    completion_count = 0
    hard_injected = 0
    soft_injected = 0
    ghost_skipped_dim = 0
    if use_pyramid_path:
        candidates_triple, completion_count = _inject_core_completion(
            existing=candidates_triple,
            canonical_core=resolved_core.canonical,
            kb_name=kb_name,
            settings=settings,
            expected_dim=expected_dim,
            dynamic_core=dynamic_core_factor,
        )
        candidates_triple, hard_injected, soft_injected, ghost_skipped_dim = _inject_ghosts(
            existing=candidates_triple,
            ghosts=ghost_tags,
            expected_dim=expected_dim,
            dynamic_core=dynamic_core_factor,
        )
    ghosts_injected_count = hard_injected + soft_injected

    # Phase 2b-2 (D8): observability — record per-call modulator metrics regardless
    # of which strategy or which downstream early-return path executes next.
    metrics = get_metrics()
    metrics.record_tag_core_tags_resolved(kb_name=kb_name, count=len(resolved_core.canonical))
    for world_kind, count in lang_applied_by_kind.items():
        for _ in range(int(count)):
            metrics.record_tag_lang_penalty_applied(
                kb_name=kb_name, query_world_kind=world_kind
            )
    if hard_injected > 0:
        metrics.record_tag_ghosts_injected(
            kb_name=kb_name, kind="hard", count=hard_injected
        )
    if soft_injected > 0:
        metrics.record_tag_ghosts_injected(
            kb_name=kb_name, kind="soft", count=soft_injected
        )
    if ghost_skipped_dim > 0:
        metrics.record_tag_ghosts_injected(
            kb_name=kb_name, kind="skipped_dim", count=ghost_skipped_dim
        )

    # Cast back to (row, weight) for dedup / context — is_core is recorded only
    # in TagBoostInfo for diagnostics; downstream pipeline behavior is unchanged.
    candidates = [(row, weight) for row, weight, _ic in candidates_triple]
    info_extra: dict = {
        **base_info_kwargs,
        "core_completion_count": int(completion_count),
        "ghosts_injected": int(ghosts_injected_count),
        "ghost_skipped_dim_mismatch": int(ghost_skipped_dim),
        "lang_penalty_applied_count": int(lang_applied_count),
        "query_world": query_world,
        # Phase 3: resonance scalar + bridge count come from boost_with_world.
        # Both default to 0 when `cross_domain_resonance_enabled` is False, so
        # every early-return TagBoostInfo carries the same shape regardless of
        # whether the resonance branch was reached.
        "cross_domain_resonance": float(boost_with_world.resonance),
        "cross_domain_bridges_count": len(boost_with_world.bridges),
        "_cross_domain_bridges": tuple(boost_with_world.bridges),
    }
    if not candidates:
        return query_vec, TagBoostInfo(
            skipped_reason="no_candidates", matrix_loaded=True, **info_extra
        )

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
            **info_extra,
        )

    dynamic = float(np.clip(boost_with_world.dynamic, cfg.dynamic_boost_min, cfg.dynamic_boost_max))
    # Phase 2b-1 (D7): record post-clamp dynamic factor + pyramid features.
    metrics.record_tag_dynamic_factor(
        kb_name=kb_name,
        strategy=str(cfg.dynamic_boost_factor_strategy),
        value=dynamic,
    )
    if pyramid_result is not None:
        metrics.record_tag_pyramid(
            kb_name=kb_name,
            levels=len(pyramid_result.levels),
            explained_energy=float(pyramid_result.total_explained_energy),
            tag_memo_activation=float(pyramid_result.features.tag_memo_activation),
            coverage=float(pyramid_result.features.coverage),
            coherence=float(pyramid_result.features.coherence),
        )
    # Phase 3: resonance metrics are gated by `cross_domain_resonance_enabled`
    # so dashboards only see traffic from callers that actually opted in. When
    # disabled the helper short-circuits at resonance=0 / bridges=() upstream.
    if cfg.cross_domain_resonance_enabled:
        metrics.record_tag_resonance_value(
            kb_name=kb_name, value=float(boost_with_world.resonance)
        )
        metrics.record_tag_resonance_bridges_count(
            kb_name=kb_name, count=len(boost_with_world.bridges)
        )
    effective_boost = float(base_tag_boost) * dynamic
    alpha = float(min(1.0, max(0.0, effective_boost)))
    if alpha <= 0.0:
        return query_vec, TagBoostInfo(
            skipped_reason="zero_alpha",
            matrix_loaded=True,
            seed_count=len(seed_entries),
            emergent_count=len(emergent_entries),
            boost_factor_applied=0.0,
            **info_extra,
        )

    fused = (1.0 - alpha) * np.asarray(query_vec, dtype=np.float32) + alpha * context
    fused_norm = float(np.linalg.norm(fused))
    if fused_norm < 1e-9:
        return query_vec, TagBoostInfo(
            skipped_reason="degenerate_fused",
            matrix_loaded=True,
            seed_count=len(seed_entries),
            emergent_count=len(emergent_entries),
            **info_extra,
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
        **info_extra,
    )
    return fused.astype(np.float32), info
