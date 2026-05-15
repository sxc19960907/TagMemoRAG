"""Phase 2b-2 modulator helpers — pure-function unit tests.

Covers `_resolve_core_tag_set`, `_resolve_core_boost_factor`, `_per_tag_core_boost`,
and `_compute_lang_penalty`. Injection helpers (`_inject_core_completion`,
`_inject_ghosts`) are exercised in a separate test module added during Step 5.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from tagmemorag.config import Settings
from tagmemorag.wave_tag_spike import (
    GhostTag,
    _compute_lang_penalty,
    _inject_core_completion,
    _inject_ghosts,
    _load_kb_tag_vectors_by_names,
    _per_tag_core_boost,
    _reset_matrix_cache_for_tests,
    _resolve_core_boost_factor,
    _resolve_core_tag_set,
    _TagVecRow,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    _reset_matrix_cache_for_tests()
    yield
    _reset_matrix_cache_for_tests()


def _settings(tmp_path: Path, *, lang_penalty_enabled: bool = False, **overrides) -> Settings:
    wave: dict = {"lang_penalty_enabled": lang_penalty_enabled, **overrides}
    return Settings(
        storage={"data_dir": str(tmp_path)},  # type: ignore[arg-type]
        manual_library={
            "registry_path": str(tmp_path / "manual_registry.sqlite3"),
            "root_dir": str(tmp_path / "product_manuals"),
        },  # type: ignore[arg-type]
        wave_phase1=wave,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# _resolve_core_tag_set
# ---------------------------------------------------------------------------


def test_resolve_core_tag_set_dedup_lowercase_and_skip_empty(tmp_path: Path):
    cfg = _settings(tmp_path)
    result = _resolve_core_tag_set(
        [" Cooling ", "cooling", "", None, "Kitchen", "  ", "kitchen"],
        kb_name="kb-x",
        settings=cfg,
    )
    assert result.input_raw == ("cooling", "kitchen")
    # No policy file ⇒ canonical falls back to raw lowercase.
    assert result.canonical == ("cooling", "kitchen")


def test_resolve_core_tag_set_unknown_tag_passes_through_when_no_policy(tmp_path: Path):
    cfg = _settings(tmp_path)
    # 'phase-2b-2-novel' is not in any policy / synonym table, no policy file exists.
    result = _resolve_core_tag_set(["phase-2b-2-novel"], kb_name="kb-x", settings=cfg)
    assert result.canonical == ("phase-2b-2-novel",)


def test_resolve_core_tag_set_resolves_synonym_to_canonical(tmp_path: Path):
    """When a tag policy exposes a synonym, _resolve_core_tag_set should rewrite it."""
    from tagmemorag import tag_governance

    # Build a policy and register it on disk so load_tag_policy picks it up.
    policy_dir = tmp_path / "data" / "tag_policies"
    policy_dir.mkdir(parents=True, exist_ok=True)
    cfg = _settings(tmp_path)
    payload = {
        "kb_name": "kb-x",
        "version": 1,
        "canonical_tags": [{"tag": "cooling"}],
        "synonyms": {"cooling-mode": "cooling"},
    }
    tag_governance.save_tag_policy("kb-x", cfg, payload)

    result = _resolve_core_tag_set(["cooling-mode"], kb_name="kb-x", settings=cfg)
    assert result.input_raw == ("cooling-mode",)
    assert result.canonical == ("cooling",)


# ---------------------------------------------------------------------------
# _compute_lang_penalty
# ---------------------------------------------------------------------------


def test_lang_penalty_disabled_returns_one(tmp_path: Path):
    cfg = _settings(tmp_path, lang_penalty_enabled=False)
    p, kind = _compute_lang_penalty("filter-cleaning", "Politics & Society", cfg)
    assert p == 1.0
    assert kind == "disabled"


def test_lang_penalty_technical_world_no_penalty(tmp_path: Path):
    cfg = _settings(tmp_path, lang_penalty_enabled=True)
    # Technical query world ⇒ langPenalty does not fire even with technical-noise tag.
    for qw in ("axis-0", "filter-cleaning", "Politics-2026"):
        p, kind = _compute_lang_penalty("filter-cleaning", qw, cfg)
        assert p == 1.0, qw
        assert kind == "technical", qw


def test_lang_penalty_unknown_world_with_tech_tag(tmp_path: Path):
    cfg = _settings(tmp_path, lang_penalty_enabled=True)
    for qw in ("Unknown", "", None):  # type: ignore[arg-type]
        p, kind = _compute_lang_penalty("filter-cleaning", qw or "", cfg)
        assert p == pytest.approx(0.4)
        assert kind == "unknown"


def test_lang_penalty_social_world_softens_via_sqrt(tmp_path: Path):
    cfg = _settings(tmp_path, lang_penalty_enabled=True)
    # 'Politics & Society' fails the technical-world regex (has space and &)
    # and matches the social regex ⇒ sqrt(0.3).
    p, kind = _compute_lang_penalty("filter-cleaning", "Politics & Society", cfg)
    assert p == pytest.approx(math.sqrt(0.3))
    assert kind == "social"


def test_lang_penalty_cross_domain_other(tmp_path: Path):
    cfg = _settings(tmp_path, lang_penalty_enabled=True)
    # Non-technical, non-social ⇒ flat 0.3.
    p, kind = _compute_lang_penalty("filter-cleaning", "Cooking & Recipes", cfg)
    assert p == pytest.approx(0.3)
    assert kind == "cross_domain_other"


def test_lang_penalty_chinese_tag_never_penalized(tmp_path: Path):
    cfg = _settings(tmp_path, lang_penalty_enabled=True)
    # CJK tag short-circuits is_tech_noise ⇒ always 1.0.
    for qw in ("Unknown", "Politics & Society", "Cooking & Recipes"):
        p, kind = _compute_lang_penalty("过滤器-清洁", qw, cfg)
        assert p == 1.0, qw
        assert kind != "social", qw


def test_lang_penalty_short_tag_never_penalized(tmp_path: Path):
    cfg = _settings(tmp_path, lang_penalty_enabled=True)
    # len(tag) <= 3 ⇒ not technical noise ⇒ no penalty even in cross-domain world.
    p, kind = _compute_lang_penalty("CO2", "Cooking & Recipes", cfg)
    assert p == 1.0
    assert kind == "cross_domain_other"


# ---------------------------------------------------------------------------
# _per_tag_core_boost & _resolve_core_boost_factor
# ---------------------------------------------------------------------------


def test_per_tag_core_boost_passes_non_core_through():
    assert _per_tag_core_boost(False, 0.0, 1.30) == 1.0
    assert _per_tag_core_boost(False, 0.5, 1.40) == 1.0
    assert _per_tag_core_boost(False, 1.0, 1.40) == 1.0


def test_per_tag_core_boost_individual_relevance_curve():
    # Source TagMemoEngine.js:144-145: coreBoost = dynamic * (0.95 + rel * 0.10).
    assert _per_tag_core_boost(True, 0.0, 1.30) == pytest.approx(1.30 * 0.95)
    assert _per_tag_core_boost(True, 0.5, 1.30) == pytest.approx(1.30 * 1.00)
    assert _per_tag_core_boost(True, 1.0, 1.30) == pytest.approx(1.30 * 1.05)
    # Out-of-range relevance is clamped.
    assert _per_tag_core_boost(True, -1.0, 1.30) == pytest.approx(1.30 * 0.95)
    assert _per_tag_core_boost(True, 5.0, 1.30) == pytest.approx(1.30 * 1.05)


class _StubFeatures:
    def __init__(self, coverage: float):
        self.coverage = coverage


def test_core_boost_factor_extremes_with_no_epa(tmp_path: Path):
    # No EPA basis ⇒ logicDepth=0; coreMetric = 0.5 * (1-coverage).
    cfg = _settings(tmp_path)
    qv = np.zeros(64, dtype=np.float32)

    # coverage=0 ⇒ coreMetric=0.5 ⇒ midpoint factor (1.30).
    f_mid = _resolve_core_boost_factor(qv, cfg, pyramid_features=None)
    assert f_mid == pytest.approx(1.30)
    f_mid2 = _resolve_core_boost_factor(qv, cfg, pyramid_features=_StubFeatures(0.0))
    assert f_mid2 == pytest.approx(1.30)

    # coverage=1.0 ⇒ coreMetric=0 ⇒ min factor (1.20).
    f_min = _resolve_core_boost_factor(qv, cfg, pyramid_features=_StubFeatures(1.0))
    assert f_min == pytest.approx(1.20)


def test_core_boost_factor_respects_custom_range(tmp_path: Path):
    cfg = _settings(tmp_path, core_boost_min=1.10, core_boost_max=1.50)
    qv = np.zeros(64, dtype=np.float32)
    f_min = _resolve_core_boost_factor(qv, cfg, pyramid_features=_StubFeatures(1.0))
    f_mid = _resolve_core_boost_factor(qv, cfg, pyramid_features=_StubFeatures(0.0))
    assert f_min == pytest.approx(1.10)
    # coverage=0 + logicDepth=0 ⇒ coreMetric=0.5 ⇒ 1.10 + 0.5*(1.50-1.10) = 1.30.
    assert f_mid == pytest.approx(1.30)


# ---------------------------------------------------------------------------
# _inject_core_completion / _inject_ghosts
# ---------------------------------------------------------------------------


def _seed_tag(cfg: Settings, kb_name: str, name: str, vector: np.ndarray) -> int:
    """Insert one canonical tag row and return its id."""
    from tagmemorag.manual_registry import create_registry

    registry = create_registry(Path(cfg.manual_library.registry_path))
    v = np.asarray(vector, dtype=np.float32)
    with registry.connection() as conn:
        conn.execute(
            "INSERT INTO tags(kb_name, name, vector, embedding_dim, embedded_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(kb_name, name) DO UPDATE SET vector=excluded.vector, "
            "embedding_dim=excluded.embedding_dim, embedded_at=excluded.embedded_at",
            (kb_name, name, v.tobytes(), int(v.shape[0]), "2026-05-16"),
        )
        row = conn.execute(
            "SELECT id FROM tags WHERE kb_name=? AND name=?", (kb_name, name)
        ).fetchone()
        conn.commit()
    return int(row["id"])


def _make_row(tag_id: int, name: str, dim: int = 8) -> _TagVecRow:
    return _TagVecRow(tag_id=tag_id, name=name, vector=np.ones(dim, dtype=np.float32))


def test_load_kb_tag_vectors_by_names_returns_only_matching_dim(tmp_path: Path):
    cfg = _settings(tmp_path)
    _seed_tag(cfg, "kb-x", "cooling", np.ones(8, dtype=np.float32))
    _seed_tag(cfg, "kb-x", "heating", np.ones(16, dtype=np.float32))  # wrong dim
    _seed_tag(cfg, "kb-y", "cooling", np.ones(8, dtype=np.float32))  # other kb

    rows = _load_kb_tag_vectors_by_names(cfg, "kb-x", ["cooling", "heating", "missing"], expected_dim=8)
    assert [r.name.lower() for r in rows] == ["cooling"]


def test_inject_core_completion_pulls_missing_from_db(tmp_path: Path):
    cfg = _settings(tmp_path)
    _seed_tag(cfg, "kb-x", "kitchen", np.ones(8, dtype=np.float32))
    existing = [(_make_row(101, "cooling"), 2.0, False)]
    out, added = _inject_core_completion(
        existing=existing,
        canonical_core=["cooling", "kitchen"],
        kb_name="kb-x",
        settings=cfg,
        expected_dim=8,
        dynamic_core=1.30,
    )
    assert added == 1
    # max_base = 2.0 / 1.30; injected weight = max_base * 1.30 = 2.0.
    assert out[-1][1] == pytest.approx(2.0)
    assert out[-1][0].name.lower() == "kitchen"
    assert out[-1][2] is True


def test_inject_core_completion_skips_already_present(tmp_path: Path):
    cfg = _settings(tmp_path)
    _seed_tag(cfg, "kb-x", "cooling", np.ones(8, dtype=np.float32))
    existing = [(_make_row(101, "Cooling"), 1.0, False)]
    out, added = _inject_core_completion(
        existing=existing,
        canonical_core=["cooling"],  # already in existing (case-insensitive)
        kb_name="kb-x",
        settings=cfg,
        expected_dim=8,
        dynamic_core=1.30,
    )
    assert added == 0
    assert out == existing


def test_inject_core_completion_empty_existing_uses_unit_max_base(tmp_path: Path):
    cfg = _settings(tmp_path)
    _seed_tag(cfg, "kb-x", "kitchen", np.ones(8, dtype=np.float32))
    out, added = _inject_core_completion(
        existing=[],
        canonical_core=["kitchen"],
        kb_name="kb-x",
        settings=cfg,
        expected_dim=8,
        dynamic_core=1.40,
    )
    assert added == 1
    # max_base=1.0 (empty existing), weight=1.0 * 1.40 = 1.40.
    assert out[0][1] == pytest.approx(1.40)


def test_inject_ghosts_dim_mismatch_skipped():
    existing = [(_make_row(101, "real", dim=8), 1.0, False)]
    out, hard, soft, skipped = _inject_ghosts(
        existing=existing,
        ghosts=[
            GhostTag(name="bad", vector=np.zeros(7, dtype=np.float32), is_core=False),
            GhostTag(name="good", vector=np.ones(8, dtype=np.float32), is_core=True),
        ],
        expected_dim=8,
        dynamic_core=1.30,
    )
    assert (hard, soft, skipped) == (1, 0, 1)
    # Existing 1 + injected 1.
    assert len(out) == 2
    assert out[-1][0].name == "good"
    assert out[-1][2] is True


def test_inject_ghosts_negative_ids_decrement_and_dont_collide():
    existing: list[tuple[_TagVecRow, float, bool]] = []
    out, hard, soft, skipped = _inject_ghosts(
        existing=existing,
        ghosts=[
            GhostTag(name="g1", vector=np.ones(4, dtype=np.float32), is_core=False),
            GhostTag(name="g2", vector=np.ones(4, dtype=np.float32), is_core=True),
            GhostTag(name="g3", vector=np.ones(4, dtype=np.float32), is_core=False),
        ],
        expected_dim=4,
        dynamic_core=1.40,
    )
    assert (hard, soft, skipped) == (1, 2, 0)
    ids = [row.tag_id for row, _w, _c in out]
    assert ids == [-1, -2, -3]
    # Hard ghost (is_core=True) gets dynamic_core multiplier; soft does not.
    assert out[0][1] == pytest.approx(1.0)
    assert out[1][1] == pytest.approx(1.40)
    assert out[2][1] == pytest.approx(1.0)


def test_inject_ghosts_empty_returns_unchanged():
    existing = [(_make_row(101, "real", dim=4), 0.5, False)]
    out, hard, soft, skipped = _inject_ghosts(
        existing=existing,
        ghosts=[],
        expected_dim=4,
        dynamic_core=1.30,
    )
    assert out == existing
    assert (hard, soft, skipped) == (0, 0, 0)


def test_inject_ghosts_skips_empty_name():
    out, hard, soft, skipped = _inject_ghosts(
        existing=[],
        ghosts=[GhostTag(name="  ", vector=np.zeros(4, dtype=np.float32), is_core=False)],
        expected_dim=4,
        dynamic_core=1.30,
    )
    assert (hard, soft, skipped) == (0, 0, 1)
    assert out == []


def test_inject_ghosts_splits_hard_soft_when_some_skipped():
    """Ensure hard/soft/skipped buckets reflect actual is_core flag, not order."""
    out, hard, soft, skipped = _inject_ghosts(
        existing=[],
        ghosts=[
            GhostTag(name="bad-hard", vector=np.zeros(7, dtype=np.float32), is_core=True),
            GhostTag(name="ok-soft", vector=np.ones(4, dtype=np.float32), is_core=False),
            GhostTag(name="bad-soft", vector=np.zeros(8, dtype=np.float32), is_core=False),
            GhostTag(name="ok-hard", vector=np.ones(4, dtype=np.float32), is_core=True),
        ],
        expected_dim=4,
        dynamic_core=1.40,
    )
    assert (hard, soft, skipped) == (1, 1, 2)
    assert len(out) == 2
