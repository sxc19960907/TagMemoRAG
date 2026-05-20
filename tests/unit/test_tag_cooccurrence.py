from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tagmemorag.manual_registry import create_registry
from tagmemorag.tag_cooccurrence import (
    COOCCURRENCE_SCHEMA_VERSION,
    CooccurrenceMatrix,
    build_cooccurrence_for_kb,
    cooccurrence_path,
    load_cooccurrence,
    save_cooccurrence,
)
from tagmemorag.config import Settings


def _seed_tags(conn, kb_name: str, tag_names: list[str]) -> dict[str, int]:
    ids: dict[str, int] = {}
    for name in tag_names:
        conn.execute(
            "INSERT INTO tags(kb_name, name) VALUES (?, ?) ON CONFLICT(kb_name, name) DO NOTHING",
            (kb_name, name),
        )
        row = conn.execute(
            "SELECT id FROM tags WHERE kb_name=? AND name=?", (kb_name, name)
        ).fetchone()
        ids[name] = int(row["id"])
    return ids


def _insert_manual_tags(conn, kb_name: str, manual_id: str, items: list[tuple[int, int]]) -> None:
    for tag_id, position in items:
        conn.execute(
            "INSERT OR REPLACE INTO manual_tags(kb_name, manual_id, tag_id, position) "
            "VALUES (?, ?, ?, ?)",
            (kb_name, manual_id, tag_id, position),
        )


@pytest.fixture()
def registry(tmp_path: Path):
    return create_registry(tmp_path / "manual_registry.sqlite3")


def test_phi_pair_4tag_fixture(registry):
    """AC2 anchor: 4-tag manual produces phi-pair weighted directed edges.

    With phi(pos, n=4) = 0.9 - 0.4 * (pos-1)/3:
        pos=1 → 0.9
        pos=2 → 0.766666...
        pos=3 → 0.633333...
        pos=4 → 0.5
    Edge weights = phi1 * phi2, source = earlier position.
    """
    kb_name = "kb-fixture"
    with registry.connection() as conn:
        ids = _seed_tags(conn, kb_name, ["a", "b", "c", "d"])
        _insert_manual_tags(
            conn,
            kb_name,
            "M1",
            [(ids["a"], 1), (ids["b"], 2), (ids["c"], 3), (ids["d"], 4)],
        )
        conn.commit()
        matrix = build_cooccurrence_for_kb(kb_name, conn)

    span_3 = 0.4 / 3.0
    phi = {1: 0.9, 2: 0.9 - span_3, 3: 0.9 - 2 * span_3, 4: 0.5}
    expected = {
        (ids["a"], ids["b"]): phi[1] * phi[2],
        (ids["a"], ids["c"]): phi[1] * phi[3],
        (ids["a"], ids["d"]): phi[1] * phi[4],
        (ids["b"], ids["c"]): phi[2] * phi[3],
        (ids["b"], ids["d"]): phi[2] * phi[4],
        (ids["c"], ids["d"]): phi[3] * phi[4],
    }
    assert matrix.edge_count == len(expected)
    for (src, dst), weight in expected.items():
        assert matrix.neighbors(src).get(dst) == pytest.approx(weight, rel=1e-6)
    # No reverse edges (direction asymmetry)
    assert matrix.neighbors(ids["d"]) == {}
    assert ids["a"] not in matrix.neighbors(ids["b"])


def test_direction_asymmetric_n2(registry):
    """n=2 manual: edge a→b exists with weight 0.45, b→a does not."""
    kb_name = "kb-n2"
    with registry.connection() as conn:
        ids = _seed_tags(conn, kb_name, ["a", "b"])
        _insert_manual_tags(conn, kb_name, "M1", [(ids["a"], 1), (ids["b"], 2)])
        conn.commit()
        matrix = build_cooccurrence_for_kb(kb_name, conn)

    assert matrix.neighbors(ids["a"]) == pytest.approx({ids["b"]: 0.45})
    assert matrix.neighbors(ids["b"]) == {}
    assert matrix.edge_count == 1


def test_weight_accumulation_across_manuals(registry):
    """Same tag pair across two manuals accumulates weight (phi1*phi2 each manual)."""
    kb_name = "kb-accum"
    with registry.connection() as conn:
        ids = _seed_tags(conn, kb_name, ["a", "b"])
        _insert_manual_tags(conn, kb_name, "M1", [(ids["a"], 1), (ids["b"], 2)])
        _insert_manual_tags(conn, kb_name, "M2", [(ids["a"], 1), (ids["b"], 2)])
        conn.commit()
        matrix = build_cooccurrence_for_kb(kb_name, conn)

    assert matrix.neighbors(ids["a"]).get(ids["b"]) == pytest.approx(0.45 + 0.45)


def test_legacy_fallback_bidirectional(registry):
    """position=0 rows fall back to symmetric edges with weight cnt*legacy_phi^2."""
    kb_name = "kb-legacy"
    with registry.connection() as conn:
        ids = _seed_tags(conn, kb_name, ["a", "b"])
        # Two manuals with both tags at position=0
        _insert_manual_tags(conn, kb_name, "M1", [(ids["a"], 0), (ids["b"], 0)])
        _insert_manual_tags(conn, kb_name, "M2", [(ids["a"], 0), (ids["b"], 0)])
        conn.commit()
        matrix = build_cooccurrence_for_kb(kb_name, conn)

    expected = 2 * 0.7 * 0.7
    assert matrix.neighbors(ids["a"]).get(ids["b"]) == pytest.approx(expected)
    assert matrix.neighbors(ids["b"]).get(ids["a"]) == pytest.approx(expected)


def test_legacy_path_does_not_run_when_all_positioned(registry):
    """Fresh Phase-0 data (all position>0) skips the legacy SQL contribution entirely."""
    kb_name = "kb-no-legacy"
    with registry.connection() as conn:
        ids = _seed_tags(conn, kb_name, ["a", "b"])
        _insert_manual_tags(conn, kb_name, "M1", [(ids["a"], 1), (ids["b"], 2)])
        conn.commit()
        matrix = build_cooccurrence_for_kb(kb_name, conn)

    # Only the directed phi-pair edge exists; reverse is absent (no legacy bidirectional injection)
    assert matrix.neighbors(ids["b"]) == {}


def test_cap_n_too_large_skipped(registry):
    """A manual with n>max_tags_per_manual contributes no edges (dirty data guard)."""
    kb_name = "kb-cap"
    with registry.connection() as conn:
        names = [f"t{i}" for i in range(101)]
        ids = _seed_tags(conn, kb_name, names)
        _insert_manual_tags(
            conn,
            kb_name,
            "M-big",
            [(ids[name], i + 1) for i, name in enumerate(names)],
        )
        conn.commit()
        matrix = build_cooccurrence_for_kb(kb_name, conn)

    assert matrix.edge_count == 0


def test_cap_n_lt_2_skipped(registry):
    """Single-tag manual contributes no edges."""
    kb_name = "kb-single"
    with registry.connection() as conn:
        ids = _seed_tags(conn, kb_name, ["a"])
        _insert_manual_tags(conn, kb_name, "M1", [(ids["a"], 1)])
        conn.commit()
        matrix = build_cooccurrence_for_kb(kb_name, conn)

    assert matrix.edge_count == 0


def test_kb_isolation(registry):
    """Different KBs don't bleed into each other."""
    with registry.connection() as conn:
        ids_a = _seed_tags(conn, "kb-a", ["x", "y"])
        ids_b = _seed_tags(conn, "kb-b", ["p", "q"])
        _insert_manual_tags(conn, "kb-a", "M1", [(ids_a["x"], 1), (ids_a["y"], 2)])
        _insert_manual_tags(conn, "kb-b", "M1", [(ids_b["p"], 1), (ids_b["q"], 2)])
        conn.commit()
        matrix_a = build_cooccurrence_for_kb("kb-a", conn)
        matrix_b = build_cooccurrence_for_kb("kb-b", conn)

    assert matrix_a.edge_count == 1
    assert matrix_b.edge_count == 1
    assert ids_b["p"] not in matrix_a.neighbors(ids_a["x"])
    assert ids_a["x"] not in matrix_b.neighbors(ids_b["p"])


def test_empty_kb_produces_empty_matrix(registry):
    """A KB with no manual_tags rows builds an empty matrix (caller skips file write)."""
    with registry.connection() as conn:
        matrix = build_cooccurrence_for_kb("kb-empty", conn)
    assert matrix.is_empty
    assert matrix.edge_count == 0
    assert matrix.kb_name == "kb-empty"


def test_save_load_roundtrip(tmp_path: Path, registry):
    """save → load yields identical edges, kb_name, schema_version, edge_count."""
    kb_name = "kb-rt"
    with registry.connection() as conn:
        ids = _seed_tags(conn, kb_name, ["a", "b", "c"])
        _insert_manual_tags(conn, kb_name, "M1", [(ids["a"], 1), (ids["b"], 2), (ids["c"], 3)])
        conn.commit()
        matrix = build_cooccurrence_for_kb(kb_name, conn)

    path = tmp_path / "rt.npz"
    save_cooccurrence(path, matrix)
    loaded = load_cooccurrence(path)

    assert loaded is not None
    assert loaded.kb_name == kb_name
    assert loaded.schema_version == COOCCURRENCE_SCHEMA_VERSION
    assert loaded.edge_count == matrix.edge_count
    for src, targets in matrix.edges.items():
        for dst, weight in targets.items():
            assert loaded.neighbors(src).get(dst) == pytest.approx(weight)


def test_determinism_two_builds_match(registry):
    """AC6 anchor: two builds over the same data produce identical edge content."""
    kb_name = "kb-det"
    with registry.connection() as conn:
        ids = _seed_tags(conn, kb_name, ["a", "b", "c", "d"])
        _insert_manual_tags(
            conn,
            kb_name,
            "M1",
            [(ids["a"], 1), (ids["b"], 2), (ids["c"], 3), (ids["d"], 4)],
        )
        _insert_manual_tags(conn, kb_name, "M2", [(ids["a"], 1), (ids["c"], 2)])
        conn.commit()
        m1 = build_cooccurrence_for_kb(kb_name, conn)
        m2 = build_cooccurrence_for_kb(kb_name, conn)

    assert m1.edges == m2.edges
    assert m1.edge_count == m2.edge_count


def test_save_refuses_empty_matrix(tmp_path: Path):
    """An empty matrix is not persisted (caller-side contract)."""
    matrix = CooccurrenceMatrix(kb_name="kb-empty", edges={}, built_at="2026-05-15", edge_count=0)
    with pytest.raises(ValueError):
        save_cooccurrence(tmp_path / "empty.npz", matrix)


def test_load_missing_file_returns_none(tmp_path: Path):
    """AC7 anchor: missing matrix file → None, callers short-circuit."""
    assert load_cooccurrence(tmp_path / "does-not-exist.npz") is None


def test_load_corrupt_file_returns_none(tmp_path: Path):
    """Corrupted npz returns None instead of raising (graceful degrade)."""
    path = tmp_path / "corrupt.npz"
    path.write_bytes(b"not a valid npz file")
    assert load_cooccurrence(path) is None


def test_load_schema_mismatch_returns_none(tmp_path: Path, registry):
    """Loader returns None when schema_version does not match."""
    kb_name = "kb-schema"
    with registry.connection() as conn:
        ids = _seed_tags(conn, kb_name, ["a", "b"])
        _insert_manual_tags(conn, kb_name, "M1", [(ids["a"], 1), (ids["b"], 2)])
        conn.commit()
        matrix = build_cooccurrence_for_kb(kb_name, conn)

    path = tmp_path / "wrong-schema.npz"
    # Write with schema_version=999
    sources = np.asarray([ids["a"]], dtype=np.int64)
    targets = np.asarray([ids["b"]], dtype=np.int64)
    weights = np.asarray([0.45], dtype=np.float32)
    with path.open("wb") as handle:
        np.savez(
            handle,
            source_ids=sources,
            target_ids=targets,
            weights=weights,
            meta_kb_name=np.asarray(kb_name, dtype=object),
            meta_built_at=np.asarray("2026-05-15", dtype=object),
            meta_schema_version=np.int32(999),
        )
    assert load_cooccurrence(path) is None


def test_atomic_write_no_tmp_file_left(tmp_path: Path, registry):
    """After a successful save, the .tmp file is gone."""
    kb_name = "kb-atomic"
    with registry.connection() as conn:
        ids = _seed_tags(conn, kb_name, ["a", "b"])
        _insert_manual_tags(conn, kb_name, "M1", [(ids["a"], 1), (ids["b"], 2)])
        conn.commit()
        matrix = build_cooccurrence_for_kb(kb_name, conn)

    path = tmp_path / "a.npz"
    save_cooccurrence(path, matrix)

    assert path.exists()
    assert not path.with_name(path.name + ".tmp").exists()


def test_cooccurrence_path_layout(tmp_path: Path):
    """Path resolves under data/_global/tag_cooccurrence/{kb}.npz."""
    cfg = Settings(storage={"data_dir": str(tmp_path)})  # type: ignore[arg-type]
    path = cooccurrence_path(cfg, "kb-test")
    assert path == tmp_path / "_global" / "tag_cooccurrence" / "kb-test.npz"
