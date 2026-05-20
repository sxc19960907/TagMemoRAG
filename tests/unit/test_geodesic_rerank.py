"""Phase 4 V8 geodesicRerank — algorithm-level unit tests.

These tests exercise the pure algorithm only: stub the registry-backed
`name → tag_id` map by injecting nodes whose metadata.tags resolve via the
test's KB seeding. We rely on the same registry plumbing that
`apply_tag_boost` uses to keep the integration honest.
"""
from __future__ import annotations

from pathlib import Path

import networkx as nx
import numpy as np
import pytest

from tagmemorag.config import Settings
from tagmemorag.manual_registry import create_registry
from tagmemorag.types import Result
from tagmemorag.wave_geodesic_rerank import geodesic_rerank


def _settings(tmp_path: Path, *, alpha: float = 0.5, min_geo_samples: int = 1) -> Settings:
    return Settings(
        storage={"data_dir": str(tmp_path)},  # type: ignore[arg-type]
        manual_library={
            "registry_path": str(tmp_path / "manual_registry.sqlite3"),
        },  # type: ignore[arg-type]
        wave_phase1={  # type: ignore[arg-type]
            "spike_enabled": True,
            "geodesic_rerank_enabled": True,
            "geodesic_alpha": alpha,
            "geodesic_min_geo_samples": min_geo_samples,
        },
    )


def _seed_canonical_tags(cfg: Settings, kb_name: str, names: list[str]) -> dict[str, int]:
    """Insert canonical tag rows so name→id resolution works inside V8."""
    registry = create_registry(cfg.manual_library.registry_path)
    name_to_id: dict[str, int] = {}
    with registry.connection() as conn:
        for name in names:
            conn.execute(
                "INSERT INTO tags(kb_name, name, vector, embedding_dim, embedded_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(kb_name, name) DO UPDATE SET vector=excluded.vector",
                (kb_name, name, np.zeros(4, dtype=np.float32).tobytes(), 4, "2026-05-15"),
            )
        for name in names:
            row = conn.execute(
                "SELECT id FROM tags WHERE kb_name=? AND name=?", (kb_name, name)
            ).fetchone()
            name_to_id[name] = int(row["id"])
        conn.commit()
    return name_to_id


def _make_graph(node_tags: dict[int, list[str]]) -> nx.Graph:
    g = nx.Graph()
    for node_id, tags in node_tags.items():
        g.add_node(node_id, text=f"chunk-{node_id}", tags=list(tags))
    return g


def _make_result(node_id: int, score: float, tags: list[str]) -> Result:
    return Result(
        node_id=node_id,
        score=score,
        text=f"chunk-{node_id}",
        header="",
        path=[],
        source_file="x.md",
        start_line=0,
        anchor_key="",
        metadata={"tags": tags},
        tags=tags,
    )


def test_l0_empty_energy_field_returns_input_order(tmp_path: Path):
    cfg = _settings(tmp_path)
    g = _make_graph({0: ["a"], 1: ["b"]})
    candidates = [_make_result(0, 0.9, ["a"]), _make_result(1, 0.5, ["b"])]

    out = geodesic_rerank(
        candidates,
        energy_field=None,
        graph=g,
        kb_name="kb-x",
        settings=cfg,
        top_k=2,
    )

    assert out.skipped_reason == "energy_field_empty"
    assert out.applied is False
    assert [r.node_id for r in out.candidates] == [0, 1]


def test_no_candidates_returns_empty(tmp_path: Path):
    cfg = _settings(tmp_path)
    g = nx.Graph()
    out = geodesic_rerank(
        [],
        energy_field={1: 1.0},
        graph=g,
        kb_name="kb-x",
        settings=cfg,
        top_k=2,
    )

    assert out.skipped_reason == "no_candidates"
    assert out.candidates == []
    assert out.applied is False


def test_l1_hit_count_below_min_samples_zeros_geo(tmp_path: Path):
    """Bumping min_geo_samples high enough makes every candidate geo=0 ⇒ L2 noop."""
    cfg = _settings(tmp_path)
    cfg.wave_phase1.geodesic_min_geo_samples = 99
    name_to_id = _seed_canonical_tags(cfg, "kb-x", ["alpha", "beta"])
    g = _make_graph({0: ["alpha"], 1: ["beta"]})
    candidates = [_make_result(0, 0.9, ["alpha"]), _make_result(1, 0.5, ["beta"])]
    energy = {name_to_id["alpha"]: 1.0, name_to_id["beta"]: 0.5}

    out = geodesic_rerank(
        candidates, energy_field=energy, graph=g, kb_name="kb-x",
        settings=cfg, top_k=2,
    )

    assert out.skipped_reason == "max_geo_zero"
    assert out.applied is False
    assert [r.node_id for r in out.candidates] == [0, 1]


def test_l2_max_geo_zero_returns_input_order(tmp_path: Path):
    """No tag in the energy field ⇒ all geo=0 ⇒ L2 noop with reason."""
    cfg = _settings(tmp_path)
    _seed_canonical_tags(cfg, "kb-x", ["alpha"])
    g = _make_graph({0: ["alpha"], 1: ["alpha"]})
    candidates = [_make_result(0, 0.9, ["alpha"]), _make_result(1, 0.5, ["alpha"])]

    # Energy refers to a tag id that is not seeded → no hits anywhere.
    out = geodesic_rerank(
        candidates,
        energy_field={9999: 1.0},
        graph=g,
        kb_name="kb-x",
        settings=cfg,
        top_k=2,
    )

    assert out.skipped_reason == "max_geo_zero"
    assert out.applied is False
    assert [r.node_id for r in out.candidates] == [0, 1]


def test_alpha_zero_pure_knn_order_preserved(tmp_path: Path):
    """alpha=0 means final = knn — V8 still applies but ranking is unchanged."""
    cfg = _settings(tmp_path)
    cfg.wave_phase1.geodesic_alpha = 0.0
    name_to_id = _seed_canonical_tags(cfg, "kb-x", ["alpha", "beta"])
    g = _make_graph({0: ["alpha"], 1: ["beta"]})
    candidates = [_make_result(0, 0.9, ["alpha"]), _make_result(1, 0.5, ["beta"])]
    # Beta has more energy but alpha=0 should ignore it.
    energy = {name_to_id["alpha"]: 0.1, name_to_id["beta"]: 1.0}

    out = geodesic_rerank(
        candidates, energy_field=energy, graph=g, kb_name="kb-x",
        settings=cfg, top_k=2,
    )

    assert out.applied is True
    assert [r.node_id for r in out.candidates] == [0, 1]
    # Scores equal the original knn since alpha=0
    assert out.candidates[0].score == pytest.approx(0.9)
    assert out.candidates[1].score == pytest.approx(0.5)


def test_alpha_one_pure_geo_reorders_by_normalized_geo(tmp_path: Path):
    """alpha=1 means final = normalized_geo — candidate with most energy wins."""
    cfg = _settings(tmp_path)
    cfg.wave_phase1.geodesic_alpha = 1.0
    name_to_id = _seed_canonical_tags(cfg, "kb-x", ["alpha", "beta"])
    g = _make_graph({0: ["alpha"], 1: ["beta"]})
    candidates = [_make_result(0, 0.9, ["alpha"]), _make_result(1, 0.1, ["beta"])]
    energy = {name_to_id["alpha"]: 0.1, name_to_id["beta"]: 1.0}

    out = geodesic_rerank(
        candidates, energy_field=energy, graph=g, kb_name="kb-x",
        settings=cfg, top_k=2,
    )

    assert out.applied is True
    # Beta has higher normalized_geo ⇒ takes top spot at alpha=1.
    assert out.candidates[0].node_id == 1
    assert out.candidates[1].node_id == 0


def test_swap_kinds_classifies_rank_changed_new_lost(tmp_path: Path):
    """Construct an oversampled pool where V8 swaps a non-top entry into top_k."""
    cfg = _settings(tmp_path)
    cfg.wave_phase1.geodesic_alpha = 1.0  # pure geo
    name_to_id = _seed_canonical_tags(cfg, "kb-x", ["alpha", "beta", "gamma"])
    g = _make_graph({0: ["alpha"], 1: ["beta"], 2: ["gamma"]})
    candidates = [
        _make_result(0, 0.9, ["alpha"]),
        _make_result(1, 0.7, ["beta"]),
        _make_result(2, 0.4, ["gamma"]),
    ]
    # Gamma has the most energy ⇒ should pull node 2 into top_k=2.
    energy = {
        name_to_id["alpha"]: 0.1,
        name_to_id["beta"]: 0.2,
        name_to_id["gamma"]: 1.0,
    }

    out = geodesic_rerank(
        candidates, energy_field=energy, graph=g, kb_name="kb-x",
        settings=cfg, top_k=2,
    )

    assert out.applied is True
    # node 2 entered top_k, displacing node 1
    assert out.swap_kinds["new_entry"] == 1
    assert out.swap_kinds["lost_entry"] == 1


def test_diagnostic_fields_attached_to_metadata(tmp_path: Path):
    cfg = _settings(tmp_path)
    name_to_id = _seed_canonical_tags(cfg, "kb-x", ["alpha"])
    g = _make_graph({0: ["alpha"]})
    candidates = [_make_result(0, 0.9, ["alpha"])]
    energy = {name_to_id["alpha"]: 0.5}

    out = geodesic_rerank(
        candidates, energy_field=energy, graph=g, kb_name="kb-x",
        settings=cfg, top_k=1,
    )

    assert out.applied is True
    md = out.candidates[0].metadata
    assert "geodesic_original_knn_score" in md
    assert md["geodesic_original_knn_score"] == pytest.approx(0.9)
    assert md["geodesic_geo_score"] == pytest.approx(0.5)
    assert md["geodesic_normalized_geo"] == pytest.approx(1.0)
    assert md["geodesic_hit_count"] == 1


def test_unknown_tags_skipped_without_error(tmp_path: Path):
    """Tags that don't resolve to a canonical id are silently dropped."""
    cfg = _settings(tmp_path)
    name_to_id = _seed_canonical_tags(cfg, "kb-x", ["alpha"])
    g = _make_graph({0: ["alpha", "completely-unknown-tag"]})
    candidates = [_make_result(0, 0.9, ["alpha", "completely-unknown-tag"])]
    energy = {name_to_id["alpha"]: 0.5}

    out = geodesic_rerank(
        candidates, energy_field=energy, graph=g, kb_name="kb-x",
        settings=cfg, top_k=1,
    )

    # Only one tag resolved + one hit observed
    assert out.applied is True
    assert out.hit_count_observed == (1,)


def test_input_candidates_not_mutated(tmp_path: Path):
    cfg = _settings(tmp_path)
    name_to_id = _seed_canonical_tags(cfg, "kb-x", ["alpha"])
    g = _make_graph({0: ["alpha"]})
    original = _make_result(0, 0.9, ["alpha"])
    candidates = [original]
    energy = {name_to_id["alpha"]: 0.5}

    out = geodesic_rerank(
        candidates, energy_field=energy, graph=g, kb_name="kb-x",
        settings=cfg, top_k=1,
    )

    # Reranked result must be a new instance with diagnostics merged in
    assert out.candidates[0] is not original
    assert original.score == 0.9  # unchanged
    assert "geodesic_original_knn_score" not in original.metadata


def test_lexical_only_path_uses_metadata_tags(tmp_path: Path):
    """Phase 4 D6.e: lexical-side candidates carry metadata.tags too — V8 must work on them.

    A 'lexical_only' candidate set is one where the `score` came from lexical
    scoring rather than KNN, but the chunk's metadata is identical (graph nodes
    are the same source-of-truth). V8 reads metadata.tags directly, so the
    distinction is invisible to the algorithm — the test pins this contract.
    """
    cfg = _settings(tmp_path)
    name_to_id = _seed_canonical_tags(cfg, "kb-x", ["alpha", "beta"])
    g = _make_graph({0: ["alpha"], 1: ["beta"]})
    # Pretend these came from lexical_search — the only difference is provenance.
    candidates = [
        _make_result(0, 0.4, ["alpha"]),  # lexical-recovered chunk
        _make_result(1, 0.3, ["beta"]),
    ]
    energy = {name_to_id["alpha"]: 0.1, name_to_id["beta"]: 1.0}
    cfg.wave_phase1.geodesic_alpha = 1.0  # pure geo to amplify the signal

    out = geodesic_rerank(
        candidates, energy_field=energy, graph=g, kb_name="kb-x",
        settings=cfg, top_k=2,
    )

    assert out.applied is True
    # node 1 (beta) has higher energy ⇒ should win at alpha=1.
    assert out.candidates[0].node_id == 1


def test_hybrid_path_swap_metric_records(tmp_path: Path):
    """Phase 4 D6.e: in a hybrid (lexical + ANN) candidate pool, swap kinds
    classify correctly when V8 swaps a non-top entry into top_k."""
    cfg = _settings(tmp_path, alpha=1.0, min_geo_samples=1)
    name_to_id = _seed_canonical_tags(cfg, "kb-x", ["a", "b", "c", "d"])
    g = _make_graph({0: ["a"], 1: ["b"], 2: ["c"], 3: ["d"]})
    # KNN-ish ordering by score: 0 > 1 > 2 > 3
    candidates = [
        _make_result(0, 0.9, ["a"]),
        _make_result(1, 0.8, ["b"]),
        _make_result(2, 0.7, ["c"]),
        _make_result(3, 0.6, ["d"]),
    ]
    # Energy strongly favors d, weakly favors c — d should jump into top_k=2,
    # bumping the worst current top_k entry.
    energy = {
        name_to_id["a"]: 0.05,
        name_to_id["b"]: 0.05,
        name_to_id["c"]: 0.05,
        name_to_id["d"]: 1.0,
    }

    out = geodesic_rerank(
        candidates, energy_field=energy, graph=g, kb_name="kb-x",
        settings=cfg, top_k=2,
    )

    assert out.applied is True
    # d entered top_k, displaced one of {0, 1}
    assert out.swap_kinds["new_entry"] >= 1
    assert out.swap_kinds["lost_entry"] >= 1
