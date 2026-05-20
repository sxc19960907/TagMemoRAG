from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Iterable

from .manuals import normalize_tag


@dataclass(frozen=True)
class StoredTag:
    id: int
    kb_name: str
    name: str
    vector: bytes | None
    embedding_dim: int | None
    embedded_at: str | None


def upsert_canonical_tag(conn: sqlite3.Connection, kb_name: str, tag_name: str) -> int:
    name = _canonical_name(tag_name)
    conn.execute(
        """
        INSERT INTO tags(kb_name, name)
        VALUES (?, ?)
        ON CONFLICT(kb_name, name) DO NOTHING
        """,
        (kb_name, name),
    )
    row = conn.execute("SELECT id FROM tags WHERE kb_name=? AND name=?", (kb_name, name)).fetchone()
    if row is None:
        raise RuntimeError("canonical tag upsert did not return a row")
    return int(row["id"])


def upsert_manual_tags(
    conn: sqlite3.Connection,
    kb_name: str,
    manual_id: str,
    metadata_tags: Iterable[str],
) -> set[int]:
    referenced: set[int] = set()
    for position, tag_name in enumerate(_dedupe_tags(metadata_tags), start=1):
        tag_id = upsert_canonical_tag(conn, kb_name, tag_name)
        conn.execute(
            """
            INSERT INTO manual_tags(kb_name, manual_id, tag_id, position)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(kb_name, manual_id, tag_id) DO UPDATE SET
                position=excluded.position
            """,
            (kb_name, manual_id, tag_id, position),
        )
        referenced.add(tag_id)

    if referenced:
        placeholders = ",".join("?" for _ in referenced)
        conn.execute(
            f"""
            DELETE FROM manual_tags
            WHERE kb_name=? AND manual_id=? AND tag_id NOT IN ({placeholders})
            """,
            (kb_name, manual_id, *sorted(referenced)),
        )
    else:
        delete_manual_tags(conn, kb_name, manual_id)
    return referenced


def delete_manual_tags(conn: sqlite3.Connection, kb_name: str, manual_id: str) -> int:
    cursor = conn.execute("DELETE FROM manual_tags WHERE kb_name=? AND manual_id=?", (kb_name, manual_id))
    return int(cursor.rowcount if cursor.rowcount is not None else 0)


def find_orphan_tags(conn: sqlite3.Connection, kb_name: str | None = None) -> list[int]:
    if kb_name is None:
        rows = conn.execute(
            """
            SELECT t.id
            FROM tags t
            LEFT JOIN manual_tags mt ON mt.tag_id = t.id
            WHERE mt.tag_id IS NULL
            ORDER BY t.id
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT t.id
            FROM tags t
            LEFT JOIN manual_tags mt ON mt.tag_id = t.id
            WHERE t.kb_name=? AND mt.tag_id IS NULL
            ORDER BY t.id
            """,
            (kb_name,),
        ).fetchall()
    return [int(row["id"]) for row in rows]


def delete_tags(conn: sqlite3.Connection, tag_ids: Iterable[int]) -> int:
    ids = sorted({int(tag_id) for tag_id in tag_ids})
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    cursor = conn.execute(f"DELETE FROM tags WHERE id IN ({placeholders})", ids)
    return int(cursor.rowcount if cursor.rowcount is not None else 0)


def lookup_tag_id(conn: sqlite3.Connection, kb_name: str, tag_name: str) -> int | None:
    name = _canonical_name(tag_name)
    row = conn.execute("SELECT id FROM tags WHERE kb_name=? AND name=?", (kb_name, name)).fetchone()
    return int(row["id"]) if row is not None else None


def iter_canonical_tags_with_vectors(
    conn: sqlite3.Connection, *, kb_name: str | None = None
) -> list[StoredTag]:
    if kb_name is None:
        rows = conn.execute(
            """
            SELECT id, kb_name, name, vector, embedding_dim, embedded_at
            FROM tags
            WHERE vector IS NOT NULL
            ORDER BY kb_name, name, id
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, kb_name, name, vector, embedding_dim, embedded_at
            FROM tags
            WHERE vector IS NOT NULL AND kb_name = ?
            ORDER BY name, id
            """,
            (kb_name,),
        ).fetchall()
    return [_stored_tag_from_row(row) for row in rows]


def _dedupe_tags(tags: Iterable[str]) -> list[str]:
    deduped: dict[str, None] = {}
    for tag in tags:
        name = _canonical_name(tag)
        if name:
            deduped.setdefault(name, None)
    return list(deduped)


def _canonical_name(tag_name: str) -> str:
    return normalize_tag(str(tag_name))


def _stored_tag_from_row(row: sqlite3.Row) -> StoredTag:
    return StoredTag(
        id=int(row["id"]),
        kb_name=str(row["kb_name"]),
        name=str(row["name"]),
        vector=row["vector"],
        embedding_dim=int(row["embedding_dim"]) if row["embedding_dim"] is not None else None,
        embedded_at=str(row["embedded_at"]) if row["embedded_at"] is not None else None,
    )
