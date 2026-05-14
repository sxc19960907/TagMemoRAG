from __future__ import annotations

import time

import numpy as np

from tagmemorag.config import ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.manual_library import library_root, mark_pending, update_manual_metadata, upsert_manual
from tagmemorag.manual_registry import create_registry
from tagmemorag.state import AppState, build_kb, start_library_rebuild


def _cfg(tmp_path) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(
            root_dir=str(tmp_path / "manuals"),
            registry_path=str(tmp_path / "manual_registry.sqlite3"),
        ),
        model={"dim": 64},
    )


def _metadata(source_file: str, manual_id: str, tags: list[str]) -> dict[str, object]:
    return {
        "manual_id": manual_id,
        "title": manual_id,
        "source_file": source_file,
        "product_category": "coffee",
        "tags": tags,
    }


def test_full_build_syncs_manual_tags_and_embeddings(tmp_path, fake_embedder):
    cfg = _cfg(tmp_path)
    upsert_manual(
        "default",
        _metadata("coffee/cm1.md", "cm1", ["Maintenance Task", "Steam Wand"]),
        b"# CM1\nClean the steam wand weekly.\n",
        cfg,
    )

    state = build_kb(library_root("default", cfg), "default", cfg, embedder=fake_embedder)
    second = build_kb(library_root("default", cfg), "default", cfg, embedder=fake_embedder)

    with create_registry(cfg.manual_library.registry_path).connection() as conn:
        rows = conn.execute(
            """
            SELECT t.name, t.vector, t.embedding_dim, mt.position
            FROM manual_tags mt
            JOIN tags t ON t.id = mt.tag_id
            WHERE mt.kb_name=? AND mt.manual_id=?
            ORDER BY mt.position
            """,
            ("default", "cm1"),
        ).fetchall()

    assert state.meta["tag_embeddings_added"] == 2
    assert state.meta["tag_embeddings_skipped"] == 0
    assert second.meta["tag_embeddings_added"] == 0
    assert second.meta["tag_embeddings_skipped"] == 2
    assert [(row["name"], row["position"]) for row in rows] == [
        ("maintenance-task", 1),
        ("steam-wand", 2),
    ]
    assert all(row["embedding_dim"] == 64 for row in rows)
    assert all(np.frombuffer(row["vector"], dtype=np.float32).shape == (64,) for row in rows)


def test_incremental_rebuild_updates_tag_links_and_removes_orphans(tmp_path, fake_embedder):
    cfg = _cfg(tmp_path)
    upsert_manual(
        "default",
        _metadata("coffee/cm1.md", "cm1", ["Maintenance Task"]),
        b"# CM1\nClean weekly.\n",
        cfg,
    )
    old_state = build_kb(library_root("default", cfg), "default", cfg, embedder=fake_embedder)
    mark_pending("default", cfg, pending=False, build_id=old_state.build_id)
    app = AppState(old_state)

    update_manual_metadata("default", "cm1", {"tags": ["Steam Wand"]}, cfg)
    task = start_library_rebuild(app, "default", cfg, embedder=fake_embedder, mode="incremental")
    for _ in range(100):
        if task.status != "running":
            break
        time.sleep(0.01)

    with create_registry(cfg.manual_library.registry_path).connection() as conn:
        names = [
            row["name"]
            for row in conn.execute(
                """
                SELECT t.name
                FROM manual_tags mt
                JOIN tags t ON t.id = mt.tag_id
                WHERE mt.kb_name=? AND mt.manual_id=?
                ORDER BY mt.position
                """,
                ("default", "cm1"),
            ).fetchall()
        ]
        all_tag_names = [row["name"] for row in conn.execute("SELECT name FROM tags ORDER BY name").fetchall()]

    assert task.status == "done"
    assert task.effective_mode == "incremental"
    assert task.tag_embeddings_added == 1
    assert task.orphan_tags_removed == 1
    assert names == ["steam-wand"]
    assert all_tag_names == ["steam-wand"]
