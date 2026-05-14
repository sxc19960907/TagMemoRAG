from __future__ import annotations

from pathlib import Path

import numpy as np

from tagmemorag.config import ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.manual_library import upsert_manual
from tagmemorag.manual_registry import create_registry
from tagmemorag.tag_governance import commit_tag_rewrite
from tagmemorag.tag_store import upsert_canonical_tag, upsert_manual_tags


def _cfg(tmp_path) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        model={"dim": 8},
    )


def _metadata(manual_id: str, source_file: str, tags: list[str]) -> dict[str, object]:
    return {
        "manual_id": manual_id,
        "title": manual_id,
        "source_file": source_file,
        "product_category": "coffee",
        "tags": tags,
    }


def _seed_sqlite_tags(cfg: Settings, kb_name: str, manual_tags: dict[str, list[str]]) -> None:
    with create_registry(PathLikeRegistry.path(cfg)).connection() as conn:
        for manual_id, tags in manual_tags.items():
            upsert_manual_tags(conn, kb_name, manual_id, tags)
        for row in conn.execute("SELECT id FROM tags").fetchall():
            vector = np.ones(8, dtype=np.float32)
            conn.execute(
                "UPDATE tags SET vector=?, embedding_dim=?, embedded_at=? WHERE id=?",
                (vector.tobytes(), 8, "2026-05-14T00:00:00+00:00", int(row["id"])),
            )


class PathLikeRegistry:
    @staticmethod
    def path(cfg: Settings):
        if cfg.manual_library.registry_path == "data/manual_registry.sqlite3":
            return Path(cfg.storage.data_dir) / "manual_registry.sqlite3"
        return cfg.manual_library.registry_path


def _tag_rows(cfg: Settings) -> list[tuple[str, bytes | None]]:
    with create_registry(PathLikeRegistry.path(cfg)).connection() as conn:
        return [(str(row["name"]), row["vector"]) for row in conn.execute("SELECT name, vector FROM tags ORDER BY name").fetchall()]


def _manual_tag_names(cfg: Settings, manual_id: str) -> list[str]:
    with create_registry(PathLikeRegistry.path(cfg)).connection() as conn:
        return [
            str(row["name"])
            for row in conn.execute(
                """
                SELECT t.name
                FROM manual_tags mt
                JOIN tags t ON t.id = mt.tag_id
                WHERE mt.manual_id=?
                ORDER BY mt.position
                """,
                (manual_id,),
            ).fetchall()
        ]


def test_merge_rewrite_updates_sqlite_links_and_deletes_orphan_source(tmp_path):
    cfg = _cfg(tmp_path)
    upsert_manual("default", _metadata("cm1", "coffee/cm1.md", ["cleaning", "maintenance"]), b"# Clean\n", cfg)
    upsert_manual("default", _metadata("cm2", "coffee/cm2.md", ["cleaning"]), b"# Clean\n", cfg)
    _seed_sqlite_tags(cfg, "default", {"cm1": ["cleaning", "maintenance"], "cm2": ["cleaning"]})

    result = commit_tag_rewrite(
        "default",
        cfg,
        source_tags=["cleaning"],
        target_tag="maintenance",
        mode="merge",
    )

    assert result.updated_count == 2
    assert _manual_tag_names(cfg, "cm1") == ["maintenance"]
    assert _manual_tag_names(cfg, "cm2") == ["maintenance"]
    assert [name for name, _vector in _tag_rows(cfg)] == ["maintenance"]


def test_rename_rewrite_creates_dirty_target_tag_and_removes_source(tmp_path):
    cfg = _cfg(tmp_path)
    upsert_manual("default", _metadata("cm1", "coffee/cm1.md", ["cleaning"]), b"# Clean\n", cfg)
    _seed_sqlite_tags(cfg, "default", {"cm1": ["cleaning"]})

    result = commit_tag_rewrite(
        "default",
        cfg,
        source_tags=["cleaning"],
        target_tag="maintenance-task",
        mode="rename",
    )

    rows = _tag_rows(cfg)
    assert result.updated_count == 1
    assert _manual_tag_names(cfg, "cm1") == ["maintenance-task"]
    assert [name for name, _vector in rows] == ["maintenance-task"]
    assert rows[0][1] is None
