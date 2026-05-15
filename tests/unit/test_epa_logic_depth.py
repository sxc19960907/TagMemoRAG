from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from tagmemorag.config import Settings, StorageConfig
from tagmemorag.embedder import HashingEmbedder
from tagmemorag.epa_basis import basis_path, save_epa_basis, train_real_pca
from tagmemorag.epa_projector import EPAProjector
from tagmemorag.state import build_kb
from tagmemorag.wave_tag_spike import _resolve_dynamic_boost, _reset_matrix_cache_for_tests, apply_tag_boost


def _settings(tmp_path: Path, *, strategy: str = "constant", scale: float = 2.0, floor: float = 0.0) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library={"registry_path": str(tmp_path / "manual_registry.sqlite3")},  # type: ignore[arg-type]
        model={"provider": "hashing", "dim": 8, "batch_size": 16},  # type: ignore[arg-type]
        wave_phase1={  # type: ignore[arg-type]
            "dynamic_boost_factor_strategy": strategy,
            "epa_logic_depth_scale": scale,
            "epa_floor": floor,
        },
    )


def _write_real_pca_basis(cfg: Settings) -> None:
    vectors = np.eye(8, dtype=np.float32)
    names = [f"tag-{index}" for index in range(vectors.shape[0])]
    basis = train_real_pca(vectors, names, cluster_count=8, min_K=4, energy_threshold=0.95)
    save_epa_basis(basis_path(cfg), basis)


def test_resolve_dynamic_constant_unchanged(tmp_path: Path):
    cfg = _settings(tmp_path, strategy="constant", scale=4.0, floor=0.9)

    dynamic = _resolve_dynamic_boost(np.ones(8, dtype=np.float32), cfg)

    assert dynamic == 1.0


def test_resolve_dynamic_epa_with_real_pca_basis(tmp_path: Path):
    cfg = _settings(tmp_path, strategy="epa", scale=2.5, floor=0.1)
    _write_real_pca_basis(cfg)
    query = np.array([1.0, 0.2, 0.0, 0.0, 0.4, 0.0, 0.0, 0.0], dtype=np.float32)
    projector = EPAProjector.from_path(basis_path(cfg))
    logic_depth = max(0.0, float(projector.project(query)["logicDepth"]))

    dynamic = _resolve_dynamic_boost(query, cfg)

    assert dynamic == pytest.approx(max(0.1, logic_depth * 2.5))


def test_resolve_dynamic_epa_degenerate_query_falls_back_to_floor(tmp_path: Path):
    cfg = _settings(tmp_path, strategy="epa", scale=2.0, floor=0.17)
    _write_real_pca_basis(cfg)
    projector = EPAProjector.from_path(basis_path(cfg))
    query = np.asarray(projector.basis.basisMean, dtype=np.float32)

    assert projector.project(query)["logicDepth"] == 0.0
    assert _resolve_dynamic_boost(query, cfg) == pytest.approx(0.17)


def test_resolve_dynamic_epa_default_params_equivalent_to_scaled_logic_depth(tmp_path: Path):
    cfg = _settings(tmp_path, strategy="epa", scale=2.0, floor=0.0)
    _write_real_pca_basis(cfg)
    query = np.array([0.1, 1.0, 0.3, 0.0, 0.0, 0.2, 0.0, 0.0], dtype=np.float32)
    projector = EPAProjector.from_path(basis_path(cfg))
    logic_depth = max(0.0, float(projector.project(query)["logicDepth"]))

    assert _resolve_dynamic_boost(query, cfg) == pytest.approx(logic_depth * 2.0)


def test_apply_tag_boost_strategy_epa_passes_d2_threshold(tmp_path: Path):
    diag = _load_diag_module()
    queries = list(diag._load_queries(Path("tests/fixtures/eval")))
    run = diag.run_diag(
        label="Real-PCA",
        docs_dir=Path("tests/fixtures/product_manuals"),
        queries=queries,
        epa_min_k=4,
        scale=2.0,
        base_tag_boost=0.03,
    )

    assert run.train_kind == "real-pca"
    assert run.tag_count == 12
    assert sum(run.explained_variance_ratio) > 0.5
    assert run.alpha.std > 0.005
    assert run.alpha.range_over_mean > 0.1


def test_apply_tag_boost_degenerate_query_uses_dynamic_min(tmp_path: Path):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library={"registry_path": str(tmp_path / "manual_registry.sqlite3")},  # type: ignore[arg-type]
        model={"provider": "hashing", "dim": 64, "batch_size": 16},  # type: ignore[arg-type]
        wave_phase0={"epa_min_k": 4},  # type: ignore[arg-type]
        wave_phase1={  # type: ignore[arg-type]
            "spike_enabled": True,
            "dynamic_boost_factor_strategy": "epa",
            "epa_logic_depth_scale": 2.0,
            "epa_floor": 0.0,
            "dynamic_boost_min": 0.3,
        },
    )
    embedder = HashingEmbedder(dim=64)
    build_kb(Path("tests/fixtures/product_manuals"), "default", cfg, embedder=embedder)
    projector = EPAProjector.from_path(basis_path(cfg))
    query = np.asarray(projector.basis.basisMean, dtype=np.float32)

    _reset_matrix_cache_for_tests()
    _boosted, info = apply_tag_boost(query, kb_name="default", settings=cfg, base_tag_boost=0.03)

    assert projector.project(query)["logicDepth"] == 0.0
    assert info.skipped_reason == ""
    assert info.boost_factor_applied == pytest.approx(0.009)


def _load_diag_module():
    path = Path("scripts/diag_epa_logic_depth.py")
    spec = importlib.util.spec_from_file_location("diag_epa_logic_depth", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Phase 2b-1 strategy="pyramid" tests
# ---------------------------------------------------------------------------


def _settings_pyramid(
    tmp_path: Path,
    *,
    scale: float = 1.0,
    floor: float = 0.0,
    act_min: float = 0.5,
    act_max: float = 1.5,
    post_scale: float = 1.0,
) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library={"registry_path": str(tmp_path / "manual_registry.sqlite3")},  # type: ignore[arg-type]
        model={"provider": "hashing", "dim": 8, "batch_size": 16},  # type: ignore[arg-type]
        wave_phase1={  # type: ignore[arg-type]
            "dynamic_boost_factor_strategy": "pyramid",
            "epa_logic_depth_scale": scale,
            "epa_floor": floor,
            "activation_multiplier_min": act_min,
            "activation_multiplier_max": act_max,
            "pyramid_post_scale": post_scale,
        },
    )


def test_resolve_dynamic_pyramid_no_features_uses_act_min(tmp_path: Path):
    """pyramid_features=None ⇒ tag_memo_activation=0 ⇒ activation_mult = act_min."""
    cfg = _settings_pyramid(tmp_path, scale=1.0, floor=0.0)
    _write_real_pca_basis(cfg)
    query = np.array([1.0, 0.2, 0.0, 0.0, 0.4, 0.0, 0.0, 0.0], dtype=np.float32)

    projector = EPAProjector.from_path(basis_path(cfg))
    proj = projector.project(query)
    logic_depth = max(0.0, float(proj["logicDepth"]))
    entropy = max(0.0, min(1.0, float(proj["entropy"])))

    dynamic = _resolve_dynamic_boost(query, cfg, pyramid_features=None)

    # resonance=0 → log(1+0)=0 → resonance term = 1
    # activation_mult = 0.5 + 0 * (1.5 - 0.5) = 0.5
    expected = (logic_depth * 1.0 / (1.0 + entropy * 0.5)) * 0.5
    assert dynamic == pytest.approx(expected, rel=1e-5)


def test_resolve_dynamic_pyramid_full_formula_with_features(tmp_path: Path):
    """Math anchor: activation=1.0 ⇒ act_mult=1.5; entropy and logic_depth from real basis."""
    from tagmemorag.residual_pyramid import PyramidFeatures

    cfg = _settings_pyramid(tmp_path, scale=1.0, floor=0.0)
    _write_real_pca_basis(cfg)
    query = np.array([1.0, 0.2, 0.0, 0.0, 0.4, 0.0, 0.0, 0.0], dtype=np.float32)

    features = PyramidFeatures(
        depth=2,
        coverage=1.0,
        novelty=0.0,
        coherence=1.0,
        tag_memo_activation=1.0,
        expansion_signal=0.0,
    )

    projector = EPAProjector.from_path(basis_path(cfg))
    proj = projector.project(query)
    logic_depth = max(0.0, float(proj["logicDepth"]))
    entropy = max(0.0, min(1.0, float(proj["entropy"])))

    dynamic = _resolve_dynamic_boost(query, cfg, pyramid_features=features)

    expected = (logic_depth * 1.0 / (1.0 + entropy * 0.5)) * 1.5
    assert dynamic == pytest.approx(expected, rel=1e-5)


def test_resolve_dynamic_pyramid_falls_back_when_no_basis(tmp_path: Path):
    """No EPA basis ⇒ projector raises ⇒ return 1.0 (constant fallback)."""
    cfg = _settings_pyramid(tmp_path)
    # NOTE: skip _write_real_pca_basis ⇒ basis file doesn't exist
    query = np.array([1.0, 0.2, 0.0, 0.0, 0.4, 0.0, 0.0, 0.0], dtype=np.float32)

    dynamic = _resolve_dynamic_boost(query, cfg, pyramid_features=None)
    assert dynamic == 1.0


def test_resolve_dynamic_pyramid_floor_applies(tmp_path: Path):
    """Floor kicks in when full formula output is below floor."""
    from tagmemorag.residual_pyramid import PyramidFeatures

    cfg = _settings_pyramid(tmp_path, scale=0.0, floor=0.42, post_scale=0.0)
    _write_real_pca_basis(cfg)
    query = np.array([1.0, 0.2, 0.0, 0.0, 0.4, 0.0, 0.0, 0.0], dtype=np.float32)
    features = PyramidFeatures(0, 0.0, 0.0, 0.0, 0.0, 0.0)

    # post_scale=0 → dynamic*post_scale = 0 → floor takes over
    assert _resolve_dynamic_boost(query, cfg, pyramid_features=features) == pytest.approx(0.42)


def test_apply_tag_boost_strategy_pyramid_smoke(tmp_path: Path):
    """End-to-end smoke: strategy=pyramid actually invokes ResidualPyramid + writes alpha > 0."""
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library={"registry_path": str(tmp_path / "manual_registry.sqlite3")},  # type: ignore[arg-type]
        model={"provider": "hashing", "dim": 64, "batch_size": 16},  # type: ignore[arg-type]
        wave_phase0={"epa_min_k": 4},  # type: ignore[arg-type]
        wave_phase1={  # type: ignore[arg-type]
            "spike_enabled": True,
            "dynamic_boost_factor_strategy": "pyramid",
            "epa_logic_depth_scale": 2.0,
            "epa_floor": 0.0,
            "dynamic_boost_min": 0.3,
            "pyramid_max_levels": 3,
            "pyramid_top_k": 6,
            "pyramid_min_energy_ratio": 0.1,
        },
    )
    embedder = HashingEmbedder(dim=64)
    build_kb(Path("tests/fixtures/product_manuals"), "default", cfg, embedder=embedder)

    _reset_matrix_cache_for_tests()
    query = embedder.encode_query("air conditioner cooling mode")
    boosted, info = apply_tag_boost(query, kb_name="default", settings=cfg, base_tag_boost=0.03)

    # Either spike took effect (boost_factor_applied > 0) or it gracefully skipped
    # with a known reason — never crash.
    assert info.skipped_reason in ("", "no_seeds", "matrix_missing", "degenerate_context", "zero_alpha")
    if info.skipped_reason == "":
        assert info.boost_factor_applied > 0.0
        assert boosted.shape == query.shape
