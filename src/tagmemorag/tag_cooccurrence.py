from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from typing import Iterable

import numpy as np

from .config import Settings


COOCCURRENCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CooccurrenceMatrix:
    kb_name: str
    edges: dict[int, dict[int, float]] = field(default_factory=dict)
    built_at: str = ""
    edge_count: int = 0
    schema_version: int = COOCCURRENCE_SCHEMA_VERSION

    def neighbors(self, tag_id: int) -> dict[int, float]:
        return self.edges.get(int(tag_id), {})

    @property
    def is_empty(self) -> bool:
        return self.edge_count == 0


def cooccurrence_dir(cfg: Settings) -> Path:
    return Path(cfg.storage.data_dir) / "_global" / "tag_cooccurrence"


def cooccurrence_path(cfg: Settings, kb_name: str) -> Path:
    safe = _safe_kb_name(kb_name)
    return cooccurrence_dir(cfg) / f"{safe}.npz"


def build_cooccurrence_for_kb(
    kb_name: str,
    conn: sqlite3.Connection,
    *,
    phi_max: float = 0.9,
    phi_min: float = 0.5,
    legacy_phi: float = 0.7,
    max_tags_per_manual: int = 100,
) -> CooccurrenceMatrix:
    """Build directed weighted co-occurrence matrix for a single KB.

    Mirrors VCPToolBox `TagMemoEngine.buildDirectedCooccurrenceMatrix`:
    - phi(pos, n) = phi_max - (phi_max - phi_min) * (pos - 1) / (n - 1)
    - edge weight = phi1 * phi2, accumulated across manuals
    - direction: earlier-position tag (source) → later-position tag (target)
    - guard: skip manuals with n<2 or n>max_tags_per_manual
    - legacy fallback (position=0 rows): weight = cnt * legacy_phi^2, written both directions
    """
    edges: dict[int, dict[int, float]] = {}

    # --- Step 2 main path: per-manual phi-pair weighting on position>0 rows ---
    rows = conn.execute(
        "SELECT manual_id, tag_id, position FROM manual_tags "
        "WHERE kb_name = ? AND position > 0 "
        "ORDER BY manual_id ASC, position ASC, tag_id ASC",
        (kb_name,),
    ).fetchall()

    pending: list[tuple[int, int]] = []  # (tag_id, position) for current manual
    current_manual: str | None = None
    for row in rows:
        manual_id = str(row["manual_id"])
        if current_manual is None:
            current_manual = manual_id
        if manual_id != current_manual:
            _flush_manual(edges, pending, phi_max, phi_min, max_tags_per_manual)
            current_manual = manual_id
            pending = []
        pending.append((int(row["tag_id"]), int(row["position"])))
    if pending:
        _flush_manual(edges, pending, phi_max, phi_min, max_tags_per_manual)

    # --- Step 3 legacy fallback: bidirectional symmetric edges for position=0 rows ---
    legacy_rows = conn.execute(
        "SELECT ft1.tag_id AS t1, ft2.tag_id AS t2, COUNT(ft1.manual_id) AS cnt "
        "FROM manual_tags ft1 "
        "JOIN manual_tags ft2 "
        "  ON ft1.kb_name = ft2.kb_name "
        " AND ft1.manual_id = ft2.manual_id "
        " AND ft1.tag_id < ft2.tag_id "
        "WHERE ft1.kb_name = ? AND (ft1.position = 0 OR ft2.position = 0) "
        "GROUP BY ft1.tag_id, ft2.tag_id "
        "ORDER BY ft1.tag_id ASC, ft2.tag_id ASC",
        (kb_name,),
    ).fetchall()
    legacy_unit = float(legacy_phi) * float(legacy_phi)
    for row in legacy_rows:
        t1 = int(row["t1"])
        t2 = int(row["t2"])
        weight = float(row["cnt"]) * legacy_unit
        _add_edge(edges, t1, t2, weight)
        _add_edge(edges, t2, t1, weight)

    edge_count = sum(len(targets) for targets in edges.values())
    return CooccurrenceMatrix(
        kb_name=kb_name,
        edges=edges,
        built_at=_now(),
        edge_count=edge_count,
    )


def save_cooccurrence(path: Path, matrix: CooccurrenceMatrix) -> None:
    """Atomically write a cooccurrence matrix to npz.

    Edges are sorted by (source_id, target_id) so two builds that yield the
    same edge set produce byte-identical files modulo `meta_built_at`.
    Empty matrices are not written (caller should skip the call when edge_count==0).
    """
    if matrix.edge_count == 0:
        raise ValueError("refusing to write empty cooccurrence matrix")
    path.parent.mkdir(parents=True, exist_ok=True)
    sources, targets, weights = _flatten_sorted(matrix.edges)

    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as handle:
        np.savez(
            handle,
            source_ids=sources,
            target_ids=targets,
            weights=weights,
            meta_kb_name=np.asarray(matrix.kb_name, dtype=object),
            meta_built_at=np.asarray(matrix.built_at or _now(), dtype=object),
            meta_schema_version=np.int32(COOCCURRENCE_SCHEMA_VERSION),
        )
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def load_cooccurrence(path: Path) -> CooccurrenceMatrix | None:
    """Load a cooccurrence matrix.

    Returns None when the file is missing, corrupt, or has an unsupported
    schema_version. Failure is silent so callers can short-circuit gracefully.
    """
    if not path.exists():
        return None
    try:
        with np.load(path, allow_pickle=True) as npz:
            schema_version = int(npz["meta_schema_version"])
            if schema_version != COOCCURRENCE_SCHEMA_VERSION:
                return None
            sources = np.asarray(npz["source_ids"], dtype=np.int64)
            targets = np.asarray(npz["target_ids"], dtype=np.int64)
            weights = np.asarray(npz["weights"], dtype=np.float32)
            kb_name = str(npz["meta_kb_name"].item())
            built_at = str(npz["meta_built_at"].item())
    except Exception:
        return None
    if sources.shape != targets.shape or sources.shape != weights.shape:
        return None
    edges: dict[int, dict[int, float]] = {}
    for s, t, w in zip(sources.tolist(), targets.tolist(), weights.tolist()):
        edges.setdefault(int(s), {})[int(t)] = float(w)
    return CooccurrenceMatrix(
        kb_name=kb_name,
        edges=edges,
        built_at=built_at,
        edge_count=int(sources.shape[0]),
        schema_version=schema_version,
    )


def _flush_manual(
    edges: dict[int, dict[int, float]],
    pending: Iterable[tuple[int, int]],
    phi_max: float,
    phi_min: float,
    max_tags_per_manual: int,
) -> None:
    items = list(pending)
    n = len(items)
    if n < 2 or n > max_tags_per_manual:
        return
    span = phi_max - phi_min
    denom = max(1, n - 1)
    for i in range(n):
        t1, p1 = items[i]
        phi1 = phi_max - span * (p1 - 1) / denom
        for j in range(i + 1, n):
            t2, p2 = items[j]
            phi2 = phi_max - span * (p2 - 1) / denom
            _add_edge(edges, t1, t2, phi1 * phi2)


def _add_edge(edges: dict[int, dict[int, float]], src: int, dst: int, weight: float) -> None:
    targets = edges.setdefault(int(src), {})
    targets[int(dst)] = targets.get(int(dst), 0.0) + float(weight)


def _flatten_sorted(edges: dict[int, dict[int, float]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    triples: list[tuple[int, int, float]] = []
    for src in sorted(edges.keys()):
        targets = edges[src]
        for dst in sorted(targets.keys()):
            triples.append((int(src), int(dst), float(targets[dst])))
    if not triples:
        return (
            np.zeros((0,), dtype=np.int64),
            np.zeros((0,), dtype=np.int64),
            np.zeros((0,), dtype=np.float32),
        )
    sources = np.asarray([t[0] for t in triples], dtype=np.int64)
    targets = np.asarray([t[1] for t in triples], dtype=np.int64)
    weights = np.asarray([t[2] for t in triples], dtype=np.float32)
    return sources, targets, weights


def _safe_kb_name(kb_name: str) -> str:
    name = str(kb_name).strip() or "default"
    return "".join(ch if (ch.isalnum() or ch in "._-") else "_" for ch in name)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
