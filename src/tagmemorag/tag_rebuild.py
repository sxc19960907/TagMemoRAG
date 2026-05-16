from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Iterable, Mapping

from .config import Settings
from .manual_registry import create_registry
from .observability.metrics import get_metrics
from .tag_cooccurrence import (
    build_cooccurrence_for_kb,
    cooccurrence_path,
    load_cooccurrence,
    save_cooccurrence,
)
from .tag_embedder import embed_dirty_tags
from .tag_intrinsic_residuals import train_intrinsic_residuals_for_kb
from .tag_store import delete_manual_tags, delete_tags, find_orphan_tags, upsert_manual_tags


@dataclass(frozen=True)
class TagRebuildReport:
    tag_embeddings_added: int = 0
    tag_embeddings_skipped: int = 0
    tag_embeddings_failed: int = 0
    orphan_tags_removed: int = 0
    tag_embedding_error: str = ""
    tag_cooccurrence_edges: int = 0
    tag_cooccurrence_error: str = ""
    tag_intrinsic_residual_rows: int = 0
    tag_intrinsic_residual_error: str = ""

    def to_dict(self) -> dict[str, int | str]:
        return {
            "tag_embeddings_added": self.tag_embeddings_added,
            "tag_embeddings_skipped": self.tag_embeddings_skipped,
            "tag_embeddings_failed": self.tag_embeddings_failed,
            "orphan_tags_removed": self.orphan_tags_removed,
            "tag_embedding_error": self.tag_embedding_error,
            "tag_cooccurrence_edges": self.tag_cooccurrence_edges,
            "tag_cooccurrence_error": self.tag_cooccurrence_error,
            "tag_intrinsic_residual_rows": self.tag_intrinsic_residual_rows,
            "tag_intrinsic_residual_error": self.tag_intrinsic_residual_error,
        }


def sync_rebuild_tags(
    kb_name: str,
    cfg: Settings,
    *,
    manual_tags_by_id: Mapping[str, Iterable[str]],
    embedder,
    manual_ids_to_clear: Iterable[str] = (),
    remove_missing_manuals: bool = False,
) -> TagRebuildReport:
    registry = create_registry(_phase0_registry_path(cfg))
    with registry.connection() as conn:
        with conn:
            if remove_missing_manuals:
                _delete_missing_manual_tags(conn, kb_name, manual_tags_by_id.keys())
            for manual_id in sorted(set(manual_ids_to_clear) - set(manual_tags_by_id)):
                delete_manual_tags(conn, kb_name, manual_id)
            for manual_id, tags in sorted(manual_tags_by_id.items()):
                upsert_manual_tags(conn, kb_name, manual_id, tags)
            orphans = find_orphan_tags(conn, kb_name)
            orphan_tags_removed = delete_tags(conn, orphans)

        dirty_count = _dirty_tag_count(conn, kb_name)
        try:
            embed_report = embed_dirty_tags(conn, kb_name, embedder, expected_dim=cfg.model.dim)
        except Exception as exc:
            metrics = get_metrics()
            metrics.record_tag_embeddings(kb_name=kb_name, outcome="failed", count=dirty_count)
            metrics.set_tags_total(kb_name=kb_name, count=_total_tag_count(conn, kb_name))
            return TagRebuildReport(
                tag_embeddings_failed=dirty_count,
                orphan_tags_removed=orphan_tags_removed,
                tag_embedding_error=type(exc).__name__,
            )

        metrics = get_metrics()
        metrics.record_tag_embeddings(kb_name=kb_name, outcome="added", count=int(embed_report.get("added", 0)))
        metrics.record_tag_embeddings(kb_name=kb_name, outcome="skipped", count=int(embed_report.get("skipped", 0)))
        metrics.record_tag_embeddings(kb_name=kb_name, outcome="failed", count=int(embed_report.get("failed", 0)))
        metrics.set_tags_total(kb_name=kb_name, count=_total_tag_count(conn, kb_name))

    cooc_edges, cooc_error = _rebuild_cooccurrence(kb_name, cfg)
    residual_rows, residual_error = _rebuild_intrinsic_residuals(kb_name, cfg)

    return TagRebuildReport(
        tag_embeddings_added=int(embed_report.get("added", 0)),
        tag_embeddings_skipped=int(embed_report.get("skipped", 0)),
        tag_embeddings_failed=int(embed_report.get("failed", 0)),
        orphan_tags_removed=orphan_tags_removed,
        tag_cooccurrence_edges=cooc_edges,
        tag_cooccurrence_error=cooc_error,
        tag_intrinsic_residual_rows=residual_rows,
        tag_intrinsic_residual_error=residual_error,
    )


def _delete_missing_manual_tags(conn, kb_name: str, manual_ids: Iterable[str]) -> None:
    ids = sorted({str(manual_id) for manual_id in manual_ids})
    if not ids:
        conn.execute("DELETE FROM manual_tags WHERE kb_name=?", (kb_name,))
        return
    placeholders = ",".join("?" for _ in ids)
    conn.execute(
        f"DELETE FROM manual_tags WHERE kb_name=? AND manual_id NOT IN ({placeholders})",
        (kb_name, *ids),
    )


def _rebuild_cooccurrence(kb_name: str, cfg: Settings) -> tuple[int, str]:
    """Rebuild and persist the directed cooccurrence matrix for one KB.

    Returns (edge_count, error_type). Failure does NOT raise — the rebuild task
    keeps going and the error is surfaced via TagRebuildReport.tag_cooccurrence_error.
    Empty matrices are not written; the file (if any) from a previous build is left
    in place — the caller can rm -rf the data dir for a hard reset.
    """
    if not cfg.wave_phase1.enabled or not cfg.wave_phase1.cooccurrence_enabled:
        return 0, ""
    metrics = get_metrics()
    started = time.perf_counter()
    try:
        registry = create_registry(_phase0_registry_path(cfg))
        with registry.connection() as conn:
            matrix = build_cooccurrence_for_kb(
                kb_name,
                conn,
                phi_max=cfg.wave_phase1.phi_max,
                phi_min=cfg.wave_phase1.phi_min,
                legacy_phi=cfg.wave_phase1.legacy_phi,
                max_tags_per_manual=cfg.wave_phase1.max_tags_per_manual,
            )
        edge_count = matrix.edge_count
        if edge_count > 0:
            save_cooccurrence(cooccurrence_path(cfg, kb_name), matrix)
        duration = time.perf_counter() - started
        metrics.record_tag_cooccurrence_rebuild(kb_name=kb_name, outcome="success", duration=duration)
        metrics.set_tag_cooccurrence_edges(kb_name=kb_name, count=edge_count)
        return edge_count, ""
    except Exception as exc:
        duration = time.perf_counter() - started
        metrics.record_tag_cooccurrence_rebuild(kb_name=kb_name, outcome="failed", duration=duration)
        return 0, type(exc).__name__


def _rebuild_intrinsic_residuals(kb_name: str, cfg: Settings) -> tuple[int, str]:
    """Train tag intrinsic residuals after cooccurrence rebuild.

    Failure is fail-soft for the rebuild path; the CLI entrypoint calls the
    underlying trainer directly when it needs a non-zero exit code.
    """
    if not cfg.wave_phase1.enabled or not cfg.wave_phase1.cooccurrence_enabled:
        return 0, ""
    try:
        matrix = load_cooccurrence(cooccurrence_path(cfg, kb_name))
        if matrix is None or matrix.edge_count == 0:
            return 0, ""
        registry = create_registry(_phase0_registry_path(cfg))
        top_n = cfg.wave_phase1.intrinsic_residual_top_n or cfg.wave_phase1.pyramid_top_k
        with registry.connection() as conn:
            report = train_intrinsic_residuals_for_kb(
                kb_name,
                conn,
                matrix,
                expected_dim=cfg.model.dim,
                top_n=int(top_n),
            )
        return report.rows_written, ""
    except Exception as exc:
        return 0, type(exc).__name__


def _dirty_tag_count(conn, kb_name: str) -> int:
    row = conn.execute("SELECT count(*) AS count FROM tags WHERE kb_name=? AND vector IS NULL", (kb_name,)).fetchone()
    return int(row["count"])


def _total_tag_count(conn, kb_name: str) -> int:
    row = conn.execute("SELECT count(*) AS count FROM tags WHERE kb_name=?", (kb_name,)).fetchone()
    return int(row["count"])


def _phase0_registry_path(cfg: Settings) -> str | Path:
    if cfg.manual_library.registry_path == "data/manual_registry.sqlite3":
        return Path(cfg.storage.data_dir) / "manual_registry.sqlite3"
    return cfg.manual_library.registry_path
