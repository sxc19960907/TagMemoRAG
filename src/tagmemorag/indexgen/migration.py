"""Lazy migration from legacy single-collection KB layout to generation-aware layout.

Architecture v2 § A4 Decision D1: rename + alias migration. On first startup
after IndexGeneration ships, each KB's legacy artifacts move into a `g1/`
subdirectory and a `meta.json` index is written. Qdrant migration uses a
collection alias so the underlying physical collection name does not change.

Idempotent: re-running on a migrated KB is a no-op. Resume-safe: a partially-
migrated KB (some files already moved) completes the move on next call.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from ..config import Settings
from ..storage.qdrant_vector import collection_name
from .meta import (
    INDEXGEN_META_FILENAME,
    INDEXGEN_META_SCHEMA_VERSION,
    KbMeta,
    ReadyGeneration,
    read_meta,
    write_meta,
)


LEGACY_FILES = (
    "graph.json",
    "vectors.npz",
    "chunk_identity.json",
    "epa_basis.npz",
    "tag_embeddings.npz",
    "tag_cooccurrence.json",
    "tag_intrinsic_residuals.npz",
    "rebuild_impact.json",
    "anchors.json",
    "meta.json",
)
LEGACY_DIRS = ("anchors",)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _has_legacy_artifacts(kb_root: Path) -> bool:
    for name in LEGACY_FILES:
        if (kb_root / name).is_file():
            return True
    for name in LEGACY_DIRS:
        if (kb_root / name).is_dir():
            return True
    return False


def _move_legacy_into_g1(kb_root: Path, g1_dir: Path) -> None:
    g1_dir.mkdir(parents=True, exist_ok=True)
    for name in LEGACY_FILES:
        src = kb_root / name
        if not src.is_file():
            continue
        dst = g1_dir / name
        if dst.exists():
            continue  # resumed migration; skip already-moved file
        os.rename(src, dst)
    for name in LEGACY_DIRS:
        src = kb_root / name
        if not src.is_dir():
            continue
        dst = g1_dir / name
        if dst.exists():
            continue
        os.rename(src, dst)


def _read_legacy_chunk_count(g1_dir: Path) -> int:
    graph_file = g1_dir / "graph.json"
    if not graph_file.is_file():
        return 0
    try:
        data = json.loads(graph_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    nodes = data.get("nodes")
    if isinstance(nodes, list):
        return len(nodes)
    return 0


def _read_legacy_build_id(g1_dir: Path) -> str:
    graph_file = g1_dir / "graph.json"
    if not graph_file.is_file():
        return ""
    try:
        data = json.loads(graph_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    meta = data.get("meta") or data.get("metadata") or {}
    if isinstance(meta, dict):
        return str(meta.get("build_id") or "")
    return ""


def _build_initial_g1_entry(g1_dir: Path, settings: Settings) -> ReadyGeneration:
    now = _now_iso()
    return ReadyGeneration(
        created_at=now,
        swap_at=now,
        retired_at=None,
        parser_version=str(getattr(settings.parser, "pdf_profile", "default")),
        chunker_version="legacy",
        embedding_model_id=settings.model.effective_embedding_model_id,
        embedding_model_version=settings.model.embedding_model_version,
        index_schema_version=int(_safe_schema_version(settings.storage.schema_version)),
        chunk_count=_read_legacy_chunk_count(g1_dir),
        build_id=_read_legacy_build_id(g1_dir),
    )


def _safe_schema_version(raw: Any) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


def _create_qdrant_alias_if_possible(
    kb_name: str, settings: Settings
) -> tuple[bool, str]:
    """Best-effort Qdrant alias creation.

    Returns (attempted, message). Attempted=False means the deployment is not
    using Qdrant or the optional dependency is missing; in that case migration
    is purely a file-system operation.

    NOTE: this function is a thin wrapper that imports qdrant_client lazily so
    NPZ deployments never need the dependency.
    """
    if settings.vector_store.provider != "qdrant":
        return False, "skipped:not_qdrant"
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        return False, "skipped:qdrant_client_missing"

    legacy = collection_name(settings.vector_store.collection_prefix, kb_name)
    new_name = collection_name(settings.vector_store.collection_prefix, kb_name, generation=1)

    client = QdrantClient(
        url=settings.vector_store.qdrant_url,
        timeout=settings.vector_store.timeout_seconds,
    )
    try:
        from qdrant_client.models import (
            CreateAlias,
            CreateAliasOperation,
        )

        operations = [
            CreateAliasOperation(
                create_alias=CreateAlias(collection_name=legacy, alias_name=new_name)
            )
        ]
        client.update_collection_aliases(change_aliases_operations=operations)
        return True, "alias_created"
    except Exception as exc:  # AlreadyExists or other; idempotent semantics
        message = type(exc).__name__
        if "already" in str(exc).lower() or "exists" in str(exc).lower():
            return True, "alias_exists"
        # Non-fatal; file-level migration still succeeded.
        return True, f"alias_failed:{message}"


def migrate_kb_to_g1_if_needed(
    kb_root: Path,
    settings: Settings,
    *,
    create_qdrant_alias: bool = True,
) -> dict[str, Any]:
    """Idempotent lazy migration to generation-aware layout.

    Returns a status dict suitable for logging. On a fully-migrated KB the
    function exits early with `status="already_migrated"`. On an empty KB
    (no legacy artifacts and no meta.json) it writes a minimal meta.json
    with `active_generation=None` and exits.

    Raises ValueError if the KB root is in an unrecoverable mid-migration
    state (g1/ exists but legacy files still present in root).
    """
    kb_root = Path(kb_root)
    kb_name = kb_root.name
    meta_path = kb_root / INDEXGEN_META_FILENAME

    existing = read_meta(kb_root)
    if existing is not None:
        return {"kb_name": kb_name, "status": "already_migrated"}

    if not kb_root.exists():
        kb_root.mkdir(parents=True, exist_ok=True)

    g1_dir = kb_root / "g1"
    has_legacy = _has_legacy_artifacts(kb_root)
    g1_exists = g1_dir.is_dir()

    if not has_legacy and not g1_exists:
        write_meta(kb_root, KbMeta.empty(kb_name))
        return {"kb_name": kb_name, "status": "empty_kb_initialised"}

    if has_legacy and g1_exists:
        # Resumed migration: g1/ has some files, root still has some files.
        # Continue moving the rest. _move_legacy_into_g1 skips files already
        # in g1/, so this is safe; but we must reject the case where the same
        # filename exists in BOTH places (genuinely corrupt state).
        for name in LEGACY_FILES:
            if (kb_root / name).is_file() and (g1_dir / name).is_file():
                raise ValueError(
                    f"Migration corrupt for {kb_name}: {name} exists in both "
                    f"{kb_root} and {g1_dir}; manual cleanup required"
                )

    _move_legacy_into_g1(kb_root, g1_dir)

    qdrant_attempted, qdrant_message = (False, "skipped:not_qdrant")
    if create_qdrant_alias:
        qdrant_attempted, qdrant_message = _create_qdrant_alias_if_possible(
            kb_name, settings
        )

    g1_entry = _build_initial_g1_entry(g1_dir, settings)
    meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name=kb_name,
        active_generation=1,
        shadow_generation=None,
        generations={1: g1_entry},
    )
    write_meta(kb_root, meta)

    return {
        "kb_name": kb_name,
        "status": "migrated",
        "g1_chunk_count": g1_entry.chunk_count,
        "qdrant_alias_attempted": qdrant_attempted,
        "qdrant_alias_result": qdrant_message,
    }
