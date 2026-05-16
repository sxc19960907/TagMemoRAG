from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tagmemorag.config import GraphConfig, Settings
from tagmemorag.graph_builder import build_graph
from tagmemorag.manual_registry import create_registry
from tagmemorag.search_runtime import execute_search, search_debug_payload
from tagmemorag.tag_cooccurrence import (
    build_cooccurrence_for_kb,
    cooccurrence_path,
    save_cooccurrence,
)
from tagmemorag.types import Chunk, GraphState
from tagmemorag.wave_tag_spike import _reset_matrix_cache_for_tests


@pytest.fixture(autouse=True)
def _clear_caches():
    _reset_matrix_cache_for_tests()
    yield
    _reset_matrix_cache_for_tests()


def _settings(tmp_path: Path, *, spike: bool = False, legacy_chunk: bool = False) -> Settings:
    return Settings(
        storage={"data_dir": str(tmp_path)},  # type: ignore[arg-type]
        manual_library={"registry_path": str(tmp_path / "manual_registry.sqlite3")},  # type: ignore[arg-type]
        wave_phase1={  # type: ignore[arg-type]
            "spike_enabled": spike,
            "seed_min_similarity": 0.0,
            "dynamic_boost_min": 0.0,
            "dynamic_boost_max": 5.0,
            "dedup_threshold": 0.999,
            "legacy_chunk_tag_boost": legacy_chunk,
        },
        search={"tag_boost": 0.5, "lexical_enabled": False, "ann_preselect_enabled": False},  # type: ignore[arg-type]
    )


def _build_graph_state(kb_name: str, dim: int = 4) -> GraphState:
    """Mini graph: 3 chunks tagged with one of {a, b, c}; same-named tag boosts that chunk."""
    chunks = [
        Chunk("text-a", "header-a", ("a",), 1, 1, "f.md", metadata={"manual_id": "M1", "tags": ["a"]}),
        Chunk("text-b", "header-b", ("b",), 1, 2, "f.md", metadata={"manual_id": "M1", "tags": ["b"]}),
        Chunk("text-c", "header-c", ("c",), 1, 3, "f.md", metadata={"manual_id": "M1", "tags": ["c"]}),
    ]
    vectors = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]], dtype=np.float32)
    graph = build_graph(chunks, vectors, GraphConfig(sim_threshold=0.99))
    return GraphState(graph=graph, vectors=vectors, kb_name=kb_name)


def _seed_phase1_data(cfg: Settings, kb_name: str) -> None:
    """Seed canonical tags+vectors and a manual_tags chain a→b→c, then write matrix."""
    registry_path = Path(cfg.manual_library.registry_path)
    registry = create_registry(registry_path)
    vecs = {
        "a": np.array([1, 0, 0, 0], dtype=np.float32),
        "b": np.array([0, 1, 0, 0], dtype=np.float32),
        "c": np.array([0, 0, 1, 0], dtype=np.float32),
    }
    ids: dict[str, int] = {}
    with registry.connection() as conn:
        for name, vec in vecs.items():
            conn.execute(
                "INSERT INTO tags(kb_name, name, vector, embedding_dim, embedded_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(kb_name, name) DO UPDATE SET vector=excluded.vector, "
                "embedding_dim=excluded.embedding_dim, embedded_at=excluded.embedded_at",
                (kb_name, name, vec.tobytes(), 4, "2026-05-15"),
            )
            row = conn.execute(
                "SELECT id FROM tags WHERE kb_name=? AND name=?", (kb_name, name)
            ).fetchone()
            ids[name] = int(row["id"])
        # Three manuals with a→b→c so the spike has multi-hop weight to traverse
        for idx, manual in enumerate(
            [
                [("a", 1), ("b", 2), ("c", 3)],
                [("a", 1), ("b", 2)],
                [("a", 1), ("b", 2)],
            ]
        ):
            for tag_name, position in manual:
                conn.execute(
                    "INSERT OR REPLACE INTO manual_tags(kb_name, manual_id, tag_id, position) "
                    "VALUES (?, ?, ?, ?)",
                    (kb_name, f"M{idx + 1}", ids[tag_name], position),
                )
        conn.commit()
        matrix = build_cooccurrence_for_kb(kb_name, conn)
    save_cooccurrence(cooccurrence_path(cfg, kb_name), matrix)


def test_spike_off_query_vec_unchanged(tmp_path: Path):
    """AC4 anchor: spike_enabled=false ⇒ no apply_tag_boost call, query_vec untouched."""
    cfg = _settings(tmp_path, spike=False)
    state = _build_graph_state("kb-x")
    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    execution = execute_search(
        state=state,
        query_vec=query,
        settings=cfg,
        top_k=3,
        source_k=3,
        steps=1,
        decay=0.7,
        amplitude_cutoff=0.01,
        aggregate="max",
        filters={"tags": ["a"]},
    )

    assert execution.tag_boost_info is None
    assert execution.legacy_tag_boost_disabled is False
    # Chunk a is in results (it matched the tag filter and the query)
    result_ids = [res.node_id for res in execution.results]
    assert 0 in result_ids


def test_spike_on_invokes_apply_and_disables_legacy(tmp_path: Path):
    """spike on + legacy default false ⇒ tag_boost_info populated, legacy boost disabled."""
    cfg = _settings(tmp_path, spike=True, legacy_chunk=False)
    state = _build_graph_state("kb-x")
    _seed_phase1_data(cfg, "kb-x")

    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    execution = execute_search(
        state=state,
        query_vec=query,
        settings=cfg,
        top_k=3,
        source_k=3,
        steps=1,
        decay=0.7,
        amplitude_cutoff=0.01,
        aggregate="max",
        filters={"tags": ["a"]},
    )

    assert execution.tag_boost_info is not None
    info = execution.tag_boost_info
    assert info.skipped_reason == ""
    assert info.matrix_loaded is True
    assert info.boost_factor_applied > 0.0
    # AC9 escape hatch off: legacy chunk-side tag boost is disabled
    assert execution.legacy_tag_boost_disabled is True


def test_legacy_chunk_tag_boost_escape_hatch(tmp_path: Path):
    """AC9 escape hatch: legacy_chunk_tag_boost=true keeps chunk-side tag bonus active."""
    cfg = _settings(tmp_path, spike=True, legacy_chunk=True)
    state = _build_graph_state("kb-x")
    _seed_phase1_data(cfg, "kb-x")

    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    execution = execute_search(
        state=state,
        query_vec=query,
        settings=cfg,
        top_k=3,
        source_k=3,
        steps=1,
        decay=0.7,
        amplitude_cutoff=0.01,
        aggregate="max",
        filters={"tags": ["a"]},
    )

    assert execution.tag_boost_info is not None
    assert execution.tag_boost_info.boost_factor_applied > 0.0
    assert execution.legacy_tag_boost_disabled is False  # escape hatch keeps legacy on


def test_spike_on_but_matrix_missing_keeps_legacy(tmp_path: Path):
    """spike on but no matrix on disk ⇒ skipped_reason='matrix_missing', legacy boost stays on."""
    cfg = _settings(tmp_path, spike=True, legacy_chunk=False)
    state = _build_graph_state("kb-x")
    # Don't seed any cooccurrence data

    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    execution = execute_search(
        state=state,
        query_vec=query,
        settings=cfg,
        top_k=3,
        source_k=3,
        steps=1,
        decay=0.7,
        amplitude_cutoff=0.01,
        aggregate="max",
        filters={"tags": ["a"]},
    )

    assert execution.tag_boost_info is not None
    assert execution.tag_boost_info.skipped_reason == "matrix_missing"
    assert execution.tag_boost_info.boost_factor_applied == 0.0
    # boost_factor_applied=0 ⇒ legacy chunk-side bonus stays active
    assert execution.legacy_tag_boost_disabled is False


def test_debug_payload_includes_tag_boost(tmp_path: Path):
    """search_debug_payload exposes tag_boost when info is present."""
    cfg = _settings(tmp_path, spike=True)
    state = _build_graph_state("kb-x")
    _seed_phase1_data(cfg, "kb-x")

    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    execution = execute_search(
        state=state,
        query_vec=query,
        settings=cfg,
        top_k=3,
        source_k=3,
        steps=1,
        decay=0.7,
        amplitude_cutoff=0.01,
        aggregate="max",
        filters={"tags": ["a"]},
    )
    payload = search_debug_payload(
        execution,
        {"source_k": 3, "steps": 1, "aggregate": "max"},
        ann_enabled=False,
    )
    assert "tag_boost" in payload
    assert payload["legacy_tag_boost_disabled"] is True
    assert isinstance(payload["tag_boost"], dict)
    assert "boost_factor_applied" in payload["tag_boost"]


def test_debug_payload_without_spike_omits_tag_boost(tmp_path: Path):
    """Spike off ⇒ no tag_boost field in debug payload (compat with Phase 0 callers)."""
    cfg = _settings(tmp_path, spike=False)
    state = _build_graph_state("kb-x")

    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    execution = execute_search(
        state=state,
        query_vec=query,
        settings=cfg,
        top_k=3,
        source_k=3,
        steps=1,
        decay=0.7,
        amplitude_cutoff=0.01,
        aggregate="max",
        filters={"tags": ["a"]},
    )
    payload = search_debug_payload(
        execution,
        {"source_k": 3, "steps": 1, "aggregate": "max"},
        ann_enabled=False,
    )
    assert "tag_boost" not in payload
    assert payload["legacy_tag_boost_disabled"] is False


def _enable_geodesic(cfg: Settings, *, alpha: float = 0.5, min_samples: int = 1) -> None:
    cfg.wave_phase1.geodesic_rerank_enabled = True
    cfg.wave_phase1.geodesic_alpha = alpha
    cfg.wave_phase1.geodesic_min_geo_samples = min_samples


def test_geodesic_off_baseline_unchanged(tmp_path: Path):
    """Phase 4: with geodesic_rerank_enabled=false, results match the spike-on baseline."""
    cfg = _settings(tmp_path, spike=True)
    state = _build_graph_state("kb-x")
    _seed_phase1_data(cfg, "kb-x")
    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    baseline = execute_search(
        state=state, query_vec=query, settings=cfg,
        top_k=3, source_k=3, steps=1, decay=0.7, amplitude_cutoff=0.01,
        aggregate="max", filters={"tags": ["a"]},
    )

    _enable_geodesic(cfg)
    # Re-build state so wave_search sees the same graph
    state2 = _build_graph_state("kb-x")
    enabled = execute_search(
        state=state2, query_vec=query, settings=cfg,
        top_k=3, source_k=3, steps=1, decay=0.7, amplitude_cutoff=0.01,
        aggregate="max", filters={"tags": ["a"]},
    )

    # When V8 actually applies and rearranges the order, scores will differ —
    # but the candidate set should remain the same after the L2 fallback.
    assert {r.node_id for r in baseline.results} == {r.node_id for r in enabled.results}


def test_geodesic_skipped_metric_when_spike_disabled(tmp_path: Path):
    """Phase 4: flag-on + spike-off ⇒ metric records skipped_reason=spike_disabled."""
    from tagmemorag.observability import metrics as metrics_module
    from prometheus_client import generate_latest

    cfg = _settings(tmp_path, spike=False)
    _enable_geodesic(cfg)
    state = _build_graph_state("kb-x")
    metrics_module.reset_metrics_for_tests()

    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    execute_search(
        state=state, query_vec=query, settings=cfg,
        top_k=3, source_k=3, steps=1, decay=0.7, amplitude_cutoff=0.01,
        aggregate="max", filters={"tags": ["a"]},
    )
    body = generate_latest(metrics_module.get_registry()).decode("utf-8")
    assert (
        'tagmemorag_geodesic_rerank_skipped_total{kb_name="kb-x",reason="spike_disabled"} 1.0'
        in body
    )
    # applied_total should NOT have a sample for kb-x — only skipped did.
    assert 'tagmemorag_geodesic_rerank_applied_total{kb_name="kb-x"} 1.0' not in body


def test_geodesic_applied_metric_when_spike_succeeds(tmp_path: Path):
    """Phase 4: flag-on + spike success ⇒ V8 actually runs (records applied or skipped).

    With our minimal 3-tag fixture, V8 will typically converge to applied=True
    when min_geo_samples=1. We accept either applied OR max_geo_zero (both valid
    runtime states) but require *something* under the geodesic_rerank_* family.
    """
    from tagmemorag.observability import metrics as metrics_module
    from prometheus_client import generate_latest

    cfg = _settings(tmp_path, spike=True)
    _enable_geodesic(cfg, alpha=0.5, min_samples=1)
    state = _build_graph_state("kb-x")
    _seed_phase1_data(cfg, "kb-x")
    metrics_module.reset_metrics_for_tests()

    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    execute_search(
        state=state, query_vec=query, settings=cfg,
        top_k=3, source_k=3, steps=1, decay=0.7, amplitude_cutoff=0.01,
        aggregate="max", filters={"tags": ["a"]},
    )

    body = generate_latest(metrics_module.get_registry()).decode("utf-8")
    fired = (
        'tagmemorag_geodesic_rerank_applied_total{kb_name="kb-x"}' in body
        or 'tagmemorag_geodesic_rerank_skipped_total{kb_name="kb-x"' in body
    )
    assert fired


def test_geodesic_filter_strict_pool_smaller_than_pool_size(tmp_path: Path):
    """Phase 4: extreme filter limits eligible candidates < pool — V8 must not crash."""
    cfg = _settings(tmp_path, spike=True)
    _enable_geodesic(cfg, min_samples=1)
    state = _build_graph_state("kb-x")
    _seed_phase1_data(cfg, "kb-x")

    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    # Only one chunk passes this filter — pool should not blow up.
    execution = execute_search(
        state=state, query_vec=query, settings=cfg,
        top_k=5, source_k=5, steps=1, decay=0.7, amplitude_cutoff=0.01,
        aggregate="max", filters={"tags": ["a"]},
    )

    # Returned at most as many results as we asked for, possibly fewer due to filter.
    assert len(execution.results) <= 5


def test_debug_payload_emits_cross_domain_bridges_only_when_present():
    """Phase 3: search_debug_payload exposes the bridges list under
    `tag_boost_debug.cross_domain_bridges` only when at least one bridge
    survived the V6 detectCrossDomainResonance threshold.

    Anchors AC10. Test bypasses execute_search and calls the payload helper
    directly so the bridges contract is locked independent of EPA fixture
    randomness.
    """
    from tagmemorag.search_runtime import SearchExecution
    from tagmemorag.wave_tag_spike import TagBoostInfo

    # No bridges ⇒ no `tag_boost_debug` key.
    info_off = TagBoostInfo(matrix_loaded=True)
    execution_off = SearchExecution(
        results=[], eligible_node_ids=set(), strategy="exact_local",
        tag_boost_info=info_off,
    )
    payload_off = search_debug_payload(
        execution_off,
        {"source_k": 3, "steps": 1, "aggregate": "max"},
        ann_enabled=False,
    )
    assert "tag_boost" in payload_off
    assert "tag_boost_debug" not in payload_off

    # With bridges ⇒ payload exposes the diagnostic list.
    bridge = {"from": "Tech", "to": "Logic", "strength": 0.5, "balance": 1.0}
    info_on = TagBoostInfo(
        matrix_loaded=True,
        cross_domain_resonance=0.5,
        cross_domain_bridges_count=1,
        _cross_domain_bridges=(bridge,),
    )
    execution_on = SearchExecution(
        results=[], eligible_node_ids=set(), strategy="exact_local",
        tag_boost_info=info_on,
    )
    payload_on = search_debug_payload(
        execution_on,
        {"source_k": 3, "steps": 1, "aggregate": "max"},
        ann_enabled=False,
    )
    assert payload_on["tag_boost_debug"] == {"cross_domain_bridges": [bridge]}
    # to_dict shape unchanged: bridges list does NOT leak into `tag_boost`.
    assert "cross_domain_bridges" not in payload_on["tag_boost"]
    assert payload_on["tag_boost"]["cross_domain_bridges_count"] == 1
    assert payload_on["tag_boost"]["cross_domain_resonance"] == 0.5
