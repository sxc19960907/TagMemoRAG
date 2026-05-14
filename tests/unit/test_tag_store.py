from __future__ import annotations

import numpy as np

from tagmemorag.manual_registry import SQLiteManualRegistry
from tagmemorag.tag_store import (
    delete_manual_tags,
    delete_tags,
    find_orphan_tags,
    iter_canonical_tags_with_vectors,
    lookup_tag_id,
    upsert_canonical_tag,
    upsert_manual_tags,
)


def test_upsert_canonical_tag_is_unique_per_kb(tmp_path):
    registry = SQLiteManualRegistry(tmp_path / "registry.sqlite3")

    with registry.connection() as conn:
        default_id = upsert_canonical_tag(conn, "default", "Temperature Setting")
        same_default_id = upsert_canonical_tag(conn, "default", "temperature_setting")
        other_kb_id = upsert_canonical_tag(conn, "washer", "temperature-setting")

    assert same_default_id == default_id
    assert other_kb_id != default_id


def test_upsert_manual_tags_writes_one_indexed_positions_and_cleans_removed_tags(tmp_path):
    registry = SQLiteManualRegistry(tmp_path / "registry.sqlite3")

    with registry.connection() as conn:
        first_ids = upsert_manual_tags(
            conn,
            "default",
            "manual-1",
            ["Fault Code", "Maintenance Task", "fault-code"],
        )
        rows = conn.execute(
            """
            SELECT t.name, mt.position
            FROM manual_tags mt
            JOIN tags t ON t.id = mt.tag_id
            WHERE mt.kb_name=? AND mt.manual_id=?
            ORDER BY mt.position
            """,
            ("default", "manual-1"),
        ).fetchall()

        second_ids = upsert_manual_tags(conn, "default", "manual-1", ["Maintenance Task"])
        remaining = conn.execute(
            """
            SELECT t.name, mt.position
            FROM manual_tags mt
            JOIN tags t ON t.id = mt.tag_id
            WHERE mt.kb_name=? AND mt.manual_id=?
            ORDER BY mt.position
            """,
            ("default", "manual-1"),
        ).fetchall()

    assert len(first_ids) == 2
    assert [(row["name"], row["position"]) for row in rows] == [
        ("fault-code", 1),
        ("maintenance-task", 2),
    ]
    assert len(second_ids) == 1
    assert [(row["name"], row["position"]) for row in remaining] == [("maintenance-task", 1)]


def test_delete_manual_tags_leaves_orphan_tags_for_explicit_cleanup(tmp_path):
    registry = SQLiteManualRegistry(tmp_path / "registry.sqlite3")

    with registry.connection() as conn:
        upsert_manual_tags(conn, "default", "manual-1", ["maintenance", "cleaning"])
        upsert_manual_tags(conn, "default", "manual-2", ["maintenance"])

        deleted = delete_manual_tags(conn, "default", "manual-1")
        orphans = find_orphan_tags(conn, "default")
        orphan_names = [
            conn.execute("SELECT name FROM tags WHERE id=?", (tag_id,)).fetchone()["name"]
            for tag_id in orphans
        ]
        deleted_orphans = delete_tags(conn, orphans)
        remaining_names = [
            row["name"]
            for row in conn.execute("SELECT name FROM tags ORDER BY name").fetchall()
        ]

    assert deleted == 2
    assert orphan_names == ["cleaning"]
    assert deleted_orphans == 1
    assert remaining_names == ["maintenance"]


def test_deleting_tags_cascades_manual_tags_and_residuals(tmp_path):
    registry = SQLiteManualRegistry(tmp_path / "registry.sqlite3")

    with registry.connection() as conn:
        tag_id = upsert_canonical_tag(conn, "default", "maintenance")
        upsert_manual_tags(conn, "default", "manual-1", ["maintenance"])
        conn.execute(
            "INSERT INTO tag_intrinsic_residuals(tag_id, residual_energy, neighbor_count) VALUES (?, ?, ?)",
            (tag_id, 1.5, 2),
        )

        deleted = delete_tags(conn, [tag_id])
        manual_tag_count = conn.execute("SELECT count(*) AS count FROM manual_tags").fetchone()["count"]
        residual_count = conn.execute("SELECT count(*) AS count FROM tag_intrinsic_residuals").fetchone()["count"]

    assert deleted == 1
    assert manual_tag_count == 0
    assert residual_count == 0


def test_lookup_and_iter_tags_with_vectors(tmp_path):
    registry = SQLiteManualRegistry(tmp_path / "registry.sqlite3")
    vector = np.array([0.1, 0.2, 0.3], dtype=np.float32).tobytes()

    with registry.connection() as conn:
        tag_id = upsert_canonical_tag(conn, "default", "maintenance")
        conn.execute(
            "UPDATE tags SET vector=?, embedding_dim=?, embedded_at=? WHERE id=?",
            (vector, 3, "2026-05-14T00:00:00+00:00", tag_id),
        )
        upsert_canonical_tag(conn, "default", "cleaning")

        found_id = lookup_tag_id(conn, "default", "Maintenance")
        missing_id = lookup_tag_id(conn, "default", "missing")
        tags = iter_canonical_tags_with_vectors(conn)

    assert found_id == tag_id
    assert missing_id is None
    assert len(tags) == 1
    assert tags[0].name == "maintenance"
    assert tags[0].vector == vector
    assert tags[0].embedding_dim == 3
