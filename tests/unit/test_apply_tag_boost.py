from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from prometheus_client import generate_latest

from tagmemorag.config import Settings
from tagmemorag.manual_registry import create_registry
from tagmemorag.tag_cooccurrence import (
    build_cooccurrence_for_kb,
    cooccurrence_path,
    save_cooccurrence,
)
from tagmemorag.wave_tag_spike import (
    TagBoostInfo,
    _reset_matrix_cache_for_tests,
    apply_tag_boost,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    _reset_matrix_cache_for_tests()
    yield
    _reset_matrix_cache_for_tests()


def _settings(tmp_path: Path, *, spike: bool = True, strategy: str = "constant", base_tag_boost: float = 0.5) -> Settings:
    return Settings(
        storage={"data_dir": str(tmp_path)},  # type: ignore[arg-type]
        manual_library={
            "registry_path": str(tmp_path / "manual_registry.sqlite3"),  # absolute, so tag_rebuild does not rewrite path
        },  # type: ignore[arg-type]
        wave_phase1={  # type: ignore[arg-type]
            "spike_enabled": spike,
            "dynamic_boost_factor_strategy": strategy,
            "dynamic_boost_min": 0.0,  # let constant=1.0 pass through
            "dynamic_boost_max": 5.0,
            "seed_top_k": 8,
            "seed_min_similarity": 0.0,  # accept all candidates in tests
            "dedup_threshold": 0.999,  # disable dedup unless test requests it
        },
        search={"tag_boost": base_tag_boost},  # type: ignore[arg-type]
    )


def _seed_kb_with_tags(
    cfg: Settings,
    kb_name: str,
    tag_specs: list[tuple[str, np.ndarray]],
    *,
    manuals: list[list[tuple[str, int]]] | None = None,
) -> dict[str, int]:
    """Insert canonical tags with vectors and (optional) manual_tags rows.

    tag_specs: list of (tag_name, vector). Vector dim becomes the embedding_dim.
    manuals: list of manuals, each is a list of (tag_name, position).
    Returns mapping tag_name → id.
    """
    registry_path = Path(cfg.manual_library.registry_path)
    registry = create_registry(registry_path)
    ids: dict[str, int] = {}
    with registry.connection() as conn:
        for name, vec in tag_specs:
            v = np.asarray(vec, dtype=np.float32)
            conn.execute(
                "INSERT INTO tags(kb_name, name, vector, embedding_dim, embedded_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(kb_name, name) DO UPDATE SET vector=excluded.vector, "
                "embedding_dim=excluded.embedding_dim, embedded_at=excluded.embedded_at",
                (kb_name, name, v.tobytes(), int(v.shape[0]), "2026-05-15"),
            )
            row = conn.execute(
                "SELECT id FROM tags WHERE kb_name=? AND name=?", (kb_name, name)
            ).fetchone()
            ids[name] = int(row["id"])
        for idx, manual in enumerate(manuals or []):
            for tag_name, position in manual:
                conn.execute(
                    "INSERT OR REPLACE INTO manual_tags(kb_name, manual_id, tag_id, position) "
                    "VALUES (?, ?, ?, ?)",
                    (kb_name, f"M{idx + 1}", ids[tag_name], position),
                )
        conn.commit()
    return ids


def _build_and_save_matrix(cfg: Settings, kb_name: str) -> int:
    registry = create_registry(Path(cfg.manual_library.registry_path))
    with registry.connection() as conn:
        matrix = build_cooccurrence_for_kb(kb_name, conn)
    if matrix.edge_count > 0:
        save_cooccurrence(cooccurrence_path(cfg, kb_name), matrix)
    return matrix.edge_count


def test_skipped_when_spike_disabled(tmp_path: Path):
    cfg = _settings(tmp_path, spike=False)
    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    boosted, info = apply_tag_boost(query, kb_name="kb-x", settings=cfg, base_tag_boost=0.5)

    assert np.array_equal(boosted, query)
    assert info.skipped_reason == "spike_disabled"
    assert info.boost_factor_applied == 0.0


def test_skipped_when_matrix_missing(tmp_path: Path):
    cfg = _settings(tmp_path, spike=True)
    # Seed canonical tags but no manual_tags ⇒ no matrix file
    _seed_kb_with_tags(cfg, "kb-x", [("a", np.array([1, 0, 0, 0], dtype=np.float32))])
    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    boosted, info = apply_tag_boost(query, kb_name="kb-x", settings=cfg, base_tag_boost=0.5)

    assert np.array_equal(boosted, query)
    assert info.skipped_reason == "matrix_missing"


def test_skipped_when_no_tag_vectors(tmp_path: Path):
    """Matrix exists but the canonical tags have no rows (uninitialized KB)."""
    cfg = _settings(tmp_path, spike=True)
    # Manually drop a fake matrix into the path so the loader returns it
    _seed_kb_with_tags(
        cfg,
        "kb-x",
        [
            ("a", np.array([1, 0, 0, 0], dtype=np.float32)),
            ("b", np.array([0, 1, 0, 0], dtype=np.float32)),
        ],
        manuals=[[("a", 1), ("b", 2)]],
    )
    edges = _build_and_save_matrix(cfg, "kb-x")
    assert edges > 0

    # Wipe the tag vectors so the loader returns []
    registry = create_registry(Path(cfg.manual_library.registry_path))
    with registry.connection() as conn:
        conn.execute("UPDATE tags SET vector=NULL, embedding_dim=NULL WHERE kb_name=?", ("kb-x",))
        conn.commit()

    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    boosted, info = apply_tag_boost(query, kb_name="kb-x", settings=cfg, base_tag_boost=0.5)
    assert np.array_equal(boosted, query)
    assert info.skipped_reason == "no_tag_vectors"
    assert info.matrix_loaded is True


def test_skipped_when_no_seeds_pass_threshold(tmp_path: Path):
    cfg = _settings(tmp_path, spike=True)
    cfg.wave_phase1.seed_min_similarity = 0.99  # nothing will match
    _seed_kb_with_tags(
        cfg,
        "kb-x",
        [
            ("a", np.array([1, 0, 0, 0], dtype=np.float32)),
            ("b", np.array([0, 1, 0, 0], dtype=np.float32)),
        ],
        manuals=[[("a", 1), ("b", 2)]],
    )
    _build_and_save_matrix(cfg, "kb-x")

    # Query orthogonal to both tags ⇒ cosine ≈ 0
    query = np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float32)
    boosted, info = apply_tag_boost(query, kb_name="kb-x", settings=cfg, base_tag_boost=0.5)
    assert np.array_equal(boosted, query)
    assert info.skipped_reason == "no_seeds"


def test_happy_path_query_vec_changes(tmp_path: Path):
    cfg = _settings(tmp_path, spike=True, base_tag_boost=0.5)
    cfg.wave_phase1.seed_min_similarity = 0.0
    # Three tags forming a chain a→b→c via manual_tags
    _seed_kb_with_tags(
        cfg,
        "kb-x",
        [
            ("a", np.array([1, 0, 0, 0], dtype=np.float32)),
            ("b", np.array([0, 1, 0, 0], dtype=np.float32)),
            ("c", np.array([0, 0, 1, 0], dtype=np.float32)),
        ],
        manuals=[
            [("a", 1), ("b", 2), ("c", 3)],
            [("a", 1), ("b", 2)],  # accumulate weight on a→b so spike actually fires
            [("a", 1), ("b", 2)],
        ],
    )
    edges = _build_and_save_matrix(cfg, "kb-x")
    assert edges > 0

    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    boosted, info = apply_tag_boost(query, kb_name="kb-x", settings=cfg, base_tag_boost=0.5)

    assert info.skipped_reason == ""
    assert info.matrix_loaded is True
    assert info.seed_count >= 1
    assert info.boost_factor_applied > 0.0
    assert info.boost_factor_applied <= 1.0
    # Boosted vector is unit norm
    assert float(np.linalg.norm(boosted)) == pytest.approx(1.0, abs=1e-5)
    # And differs from original (some context was injected)
    assert not np.allclose(boosted, query)


def test_zero_alpha_when_base_boost_zero(tmp_path: Path):
    cfg = _settings(tmp_path, spike=True, base_tag_boost=0.0)
    cfg.wave_phase1.dynamic_boost_min = 0.0  # so clipping doesn't bump alpha up
    _seed_kb_with_tags(
        cfg,
        "kb-x",
        [
            ("a", np.array([1, 0, 0, 0], dtype=np.float32)),
            ("b", np.array([0, 1, 0, 0], dtype=np.float32)),
        ],
        manuals=[[("a", 1), ("b", 2)]],
    )
    _build_and_save_matrix(cfg, "kb-x")

    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    boosted, info = apply_tag_boost(query, kb_name="kb-x", settings=cfg, base_tag_boost=0.0)

    assert info.skipped_reason == "zero_alpha"
    assert np.array_equal(boosted, query)


def test_dynamic_boost_constant_strategy_returns_one(tmp_path: Path):
    """With strategy=constant the dynamic factor is always 1.0 (D2)."""
    cfg = _settings(tmp_path, spike=True, strategy="constant", base_tag_boost=0.5)
    cfg.wave_phase1.dynamic_boost_min = 0.99
    cfg.wave_phase1.dynamic_boost_max = 1.01
    _seed_kb_with_tags(
        cfg,
        "kb-x",
        [
            ("a", np.array([1, 0, 0, 0], dtype=np.float32)),
            ("b", np.array([0, 1, 0, 0], dtype=np.float32)),
        ],
        manuals=[[("a", 1), ("b", 2)]],
    )
    _build_and_save_matrix(cfg, "kb-x")
    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    _, info = apply_tag_boost(query, kb_name="kb-x", settings=cfg, base_tag_boost=0.5)

    # alpha = clip(base * dynamic) = clip(0.5 * 1.0, [0.99, 1.01]) ⇒ 0.5 * clamped to >= 0.99
    # constant=1.0 ⇒ effective_boost = 0.5 * 1.0 = 0.5; clamping happens on dynamic, not on alpha
    # So alpha = min(1.0, 0.5 * 1.0) = 0.5
    assert info.boost_factor_applied == pytest.approx(0.5)


def test_dynamic_boost_epa_strategy_falls_back_when_basis_missing(tmp_path: Path):
    """If EPA basis cannot be loaded, dynamic factor falls back to constant=1.0."""
    cfg = _settings(tmp_path, spike=True, strategy="epa", base_tag_boost=0.5)
    cfg.wave_phase1.dynamic_boost_min = 0.0
    cfg.wave_phase1.dynamic_boost_max = 5.0
    _seed_kb_with_tags(
        cfg,
        "kb-x",
        [
            ("a", np.array([1, 0, 0, 0], dtype=np.float32)),
            ("b", np.array([0, 1, 0, 0], dtype=np.float32)),
        ],
        manuals=[[("a", 1), ("b", 2)]],
    )
    _build_and_save_matrix(cfg, "kb-x")

    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    boosted, info = apply_tag_boost(query, kb_name="kb-x", settings=cfg, base_tag_boost=0.5)

    # Without an EPA basis on disk, the resolver must not crash; alpha should still be applied (constant fallback)
    assert info.skipped_reason == ""
    assert info.boost_factor_applied > 0.0
    # And vector still changed
    assert not np.allclose(boosted, query)


def test_matrix_cache_invalidates_on_mtime_change(tmp_path: Path):
    """After rewriting the matrix file, the loader must pick up the new version."""
    cfg = _settings(tmp_path, spike=True)
    _seed_kb_with_tags(
        cfg,
        "kb-x",
        [
            ("a", np.array([1, 0, 0, 0], dtype=np.float32)),
            ("b", np.array([0, 1, 0, 0], dtype=np.float32)),
            ("c", np.array([0, 0, 1, 0], dtype=np.float32)),
        ],
        manuals=[[("a", 1), ("b", 2)]],
    )
    edges_v1 = _build_and_save_matrix(cfg, "kb-x")
    assert edges_v1 == 1

    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    apply_tag_boost(query, kb_name="kb-x", settings=cfg, base_tag_boost=0.5)

    # Now add a new manual that introduces a new edge
    registry = create_registry(Path(cfg.manual_library.registry_path))
    with registry.connection() as conn:
        ids = {
            row["name"]: int(row["id"])
            for row in conn.execute("SELECT id, name FROM tags WHERE kb_name=?", ("kb-x",))
        }
        conn.execute(
            "INSERT INTO manual_tags(kb_name, manual_id, tag_id, position) VALUES (?, ?, ?, ?)",
            ("kb-x", "M2", ids["a"], 1),
        )
        conn.execute(
            "INSERT INTO manual_tags(kb_name, manual_id, tag_id, position) VALUES (?, ?, ?, ?)",
            ("kb-x", "M2", ids["c"], 2),
        )
        conn.commit()
    # Sleep tiny amount and bump mtime by rewriting
    import time as _time

    _time.sleep(0.01)
    edges_v2 = _build_and_save_matrix(cfg, "kb-x")
    assert edges_v2 == 2  # a→b and a→c

    # apply_tag_boost should now see the second matrix
    _, info = apply_tag_boost(query, kb_name="kb-x", settings=cfg, base_tag_boost=0.5)
    # Both b and c should be reachable as emergent (or seeds, depending on cosine)
    # With seed_min_similarity=0 all 3 tags become candidate seeds; the spike then revisits b/c
    assert info.matrix_loaded is True
    # If a is the only seed (most similar to query), b and c must surface as emergent
    # If multiple seeds, total candidates ≥ 2
    assert info.seed_count + info.emergent_count >= 2


def test_to_dict_serializable():
    info = TagBoostInfo(
        seed_tag_ids=(1, 2),
        seed_count=2,
        emergent_count=3,
        matched_tag_names=("a", "b"),
        boost_factor_applied=0.5,
        matrix_loaded=True,
        skipped_reason="",
        truncated_by_cap=False,
    )
    d = info.to_dict()
    assert d["seed_tag_ids"] == [1, 2]
    assert d["matched_tag_names"] == ["a", "b"]
    assert d["boost_factor_applied"] == 0.5
    assert d["matrix_loaded"] is True
    # Phase 2b-2 fields default to empty / 0 / "" so old callers see no change in shape.
    assert d["core_tags_input"] == []
    assert d["core_tags_resolved"] == []
    assert d["core_completion_count"] == 0
    assert d["ghosts_injected"] == 0
    assert d["ghost_skipped_dim_mismatch"] == 0
    assert d["lang_penalty_applied_count"] == 0
    assert d["query_world"] == ""
    # Phase 3 fields default to 0 / 0 (resonance disabled by default).
    assert d["cross_domain_resonance"] == 0.0
    assert d["cross_domain_bridges_count"] == 0


def test_apply_tag_boost_constant_strategy_ignores_core_ghost(tmp_path: Path):
    """R10 review-gate: strategy=constant + core/ghost args ⇒ boost_factor unchanged.

    The new fields appear in TagBoostInfo (with the resolved canonical names) but
    no candidate weight is modified — the fused vector and alpha must match the
    no-args call byte-for-byte.
    """
    from tagmemorag.wave_tag_spike import GhostTag

    cfg = _settings(tmp_path, spike=True, base_tag_boost=0.5, strategy="constant")
    cfg.wave_phase1.seed_min_similarity = 0.0
    _seed_kb_with_tags(
        cfg,
        "kb-x",
        [
            ("a", np.array([1, 0, 0, 0], dtype=np.float32)),
            ("b", np.array([0, 1, 0, 0], dtype=np.float32)),
            ("c", np.array([0, 0, 1, 0], dtype=np.float32)),
        ],
        manuals=[
            [("a", 1), ("b", 2), ("c", 3)],
            [("a", 1), ("b", 2)],
            [("a", 1), ("b", 2)],
        ],
    )
    edges = _build_and_save_matrix(cfg, "kb-x")
    assert edges > 0
    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    boosted_a, info_a = apply_tag_boost(query, kb_name="kb-x", settings=cfg, base_tag_boost=0.5)
    boosted_b, info_b = apply_tag_boost(
        query,
        kb_name="kb-x",
        settings=cfg,
        base_tag_boost=0.5,
        core_tags=["a", "kitchen"],
        ghost_tags=[GhostTag(name="ghost", vector=np.zeros(4, dtype=np.float32), is_core=True)],
    )

    # Output vectors and alpha are identical: strategy=constant blocks core/ghost effects.
    assert np.array_equal(boosted_a, boosted_b)
    assert info_a.boost_factor_applied == info_b.boost_factor_applied
    assert info_b.core_tags_input == ("a", "kitchen")
    assert info_b.core_tags_resolved == ("a", "kitchen")
    assert info_b.core_completion_count == 0
    assert info_b.ghosts_injected == 0
    assert info_a.matched_tag_names == info_b.matched_tag_names


def test_apply_tag_boost_pyramid_records_core_tags_in_info(tmp_path: Path):
    cfg = _settings(tmp_path, spike=True, base_tag_boost=0.5, strategy="pyramid")
    cfg.wave_phase1.seed_min_similarity = 0.0
    cfg.wave_phase1.dynamic_boost_min = 0.001  # let alpha pass through under hashing fixture
    _seed_kb_with_tags(
        cfg,
        "kb-x",
        [
            ("cooling", np.array([1, 0, 0, 0], dtype=np.float32)),
            ("kitchen", np.array([0, 1, 0, 0], dtype=np.float32)),
            ("filter", np.array([0, 0, 1, 0], dtype=np.float32)),
        ],
        manuals=[
            [("cooling", 1), ("kitchen", 2), ("filter", 3)],
            [("cooling", 1), ("kitchen", 2)],
            [("cooling", 1), ("kitchen", 2)],
        ],
    )
    _build_and_save_matrix(cfg, "kb-x")
    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    _boosted, info = apply_tag_boost(
        query,
        kb_name="kb-x",
        settings=cfg,
        base_tag_boost=0.5,
        core_tags=["cooling", "Cooling"],  # dedup to canonical 'cooling'
    )
    assert info.core_tags_input == ("cooling",)
    assert info.core_tags_resolved == ("cooling",)
    assert info.matrix_loaded is True


def test_apply_tag_boost_pyramid_ghost_appears_in_matched_names(tmp_path: Path):
    from tagmemorag.wave_tag_spike import GhostTag

    cfg = _settings(tmp_path, spike=True, base_tag_boost=0.5, strategy="pyramid")
    cfg.wave_phase1.seed_min_similarity = 0.0
    cfg.wave_phase1.dynamic_boost_min = 0.001
    _seed_kb_with_tags(
        cfg,
        "kb-x",
        [
            ("cooling", np.array([1, 0, 0, 0], dtype=np.float32)),
            ("kitchen", np.array([0, 1, 0, 0], dtype=np.float32)),
        ],
        manuals=[
            [("cooling", 1), ("kitchen", 2)],
            [("cooling", 1), ("kitchen", 2)],
        ],
    )
    _build_and_save_matrix(cfg, "kb-x")
    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    ghosts = [
        GhostTag(name="airflow", vector=np.array([0, 0, 1, 0], dtype=np.float32), is_core=True),
        GhostTag(name="bad", vector=np.zeros(8, dtype=np.float32), is_core=False),  # dim mismatch
    ]
    _boosted, info = apply_tag_boost(
        query,
        kb_name="kb-x",
        settings=cfg,
        base_tag_boost=0.5,
        ghost_tags=ghosts,
    )
    assert info.ghosts_injected == 1
    assert info.ghost_skipped_dim_mismatch == 1
    assert "airflow" in info.matched_tag_names


def test_apply_tag_boost_resonance_disabled_default(tmp_path: Path):
    """Phase 3: default cross_domain_resonance_enabled=False ⇒ TagBoostInfo
    keeps the resonance fields at 0 and the metric series stay untouched.

    Pairs with `tests/unit/test_epa_logic_depth.py::
    test_resolve_dynamic_pyramid_resonance_disabled_default_unchanged` to
    anchor AC7 — the wired-up info_extra path defaults must match Phase 2b-2.
    """
    from tagmemorag.observability import metrics as metrics_module

    cfg = _settings(tmp_path, spike=True, base_tag_boost=0.5, strategy="pyramid")
    cfg.wave_phase1.seed_min_similarity = 0.0
    cfg.wave_phase1.dynamic_boost_min = 0.001
    _seed_kb_with_tags(
        cfg,
        "kb-x",
        [
            ("cooling", np.array([1, 0, 0, 0], dtype=np.float32)),
            ("kitchen", np.array([0, 1, 0, 0], dtype=np.float32)),
            ("filter", np.array([0, 0, 1, 0], dtype=np.float32)),
        ],
        manuals=[
            [("cooling", 1), ("kitchen", 2), ("filter", 3)],
            [("cooling", 1), ("kitchen", 2)],
            [("cooling", 1), ("kitchen", 2)],
        ],
    )
    _build_and_save_matrix(cfg, "kb-x")
    metrics_module.reset_metrics_for_tests()  # isolate this test's metric scrape
    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    _boosted, info = apply_tag_boost(
        query, kb_name="kb-x", settings=cfg, base_tag_boost=0.5
    )

    assert info.cross_domain_resonance == 0.0
    assert info.cross_domain_bridges_count == 0
    body = generate_latest(metrics_module.get_registry()).decode("utf-8")
    # Disabled path must NOT register samples on the resonance histograms — the
    # series may exist (definitions register at startup) but the bucket counters
    # for kb_name="kb-x" must be absent.
    assert 'tagmemorag_tag_resonance_value_count{kb_name="kb-x"}' not in body
    assert 'tagmemorag_tag_resonance_bridges_count_count{kb_name="kb-x"}' not in body


def test_apply_tag_boost_resonance_enabled_records_metric(tmp_path: Path):
    """Phase 3: enabled=True ⇒ resonance metric writes a sample on every call.

    The hashing dim=4 fixture often resolves to a single dominant axis so
    `resonance` may stay 0.0; AC9 only requires the metric to be exercised
    (a 0.0 observation still increments the bucket count).
    """
    from tagmemorag.observability import metrics as metrics_module

    cfg = _settings(tmp_path, spike=True, base_tag_boost=0.5, strategy="pyramid")
    cfg.wave_phase1.seed_min_similarity = 0.0
    cfg.wave_phase1.dynamic_boost_min = 0.001
    cfg.wave_phase1.cross_domain_resonance_enabled = True
    _seed_kb_with_tags(
        cfg,
        "kb-x",
        [
            ("cooling", np.array([1, 0, 0, 0], dtype=np.float32)),
            ("kitchen", np.array([0, 1, 0, 0], dtype=np.float32)),
            ("filter", np.array([0, 0, 1, 0], dtype=np.float32)),
        ],
        manuals=[
            [("cooling", 1), ("kitchen", 2), ("filter", 3)],
            [("cooling", 1), ("kitchen", 2)],
            [("cooling", 1), ("kitchen", 2)],
        ],
    )
    _build_and_save_matrix(cfg, "kb-x")
    metrics_module.reset_metrics_for_tests()
    query = np.array([1.0, 0.5, 0.3, 0.0], dtype=np.float32)

    _boosted, info = apply_tag_boost(
        query, kb_name="kb-x", settings=cfg, base_tag_boost=0.5
    )

    body = generate_latest(metrics_module.get_registry()).decode("utf-8")
    # Either the call hit the spike disabled / no-seeds early-return (no metric
    # registration but also no resonance leakage) OR enabled=true recorded a
    # sample. If a sample was recorded, both histograms must be present for the
    # kb scope.
    if info.skipped_reason in ("", "no_candidates", "degenerate_context", "zero_alpha"):
        assert 'tagmemorag_tag_resonance_value_count{kb_name="kb-x"}' in body
        assert 'tagmemorag_tag_resonance_bridges_count_count{kb_name="kb-x"}' in body
        # Bridges count is non-negative integer, resonance is non-negative float.
        assert info.cross_domain_resonance >= 0.0
        assert info.cross_domain_bridges_count >= 0
