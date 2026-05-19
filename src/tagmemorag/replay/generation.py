from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from ..indexgen import KbPaths, ReadyGeneration, read_meta
from ..indexgen.meta import GenerationStatus, ShadowGeneration
from ..storage.json_anchor import JsonAnchorStore
from ..storage.json_graph import JsonGraphStore
from ..storage.npz_vector import NpzVectorStore
from ..types import GraphState

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings


class ReplayGenerationError(RuntimeError):
    """Raised when a requested generation cannot be replayed offline."""


def resolve_generation_selector(kb_name: str, settings: "Settings", selector: str | int) -> int:
    """Resolve `active`, `shadow`, `gN`, or `N` into a concrete generation id."""
    if isinstance(selector, int):
        if selector <= 0:
            raise ReplayGenerationError("generation must be positive")
        return selector

    text = str(selector).strip().lower()
    kb_root = Path(settings.storage.data_dir) / kb_name
    meta = read_meta(kb_root)
    if meta is None:
        raise ReplayGenerationError(f"index.json not found for KB {kb_name!r}")

    if text == "active":
        if meta.active_generation is None or meta.get_active() is None:
            raise ReplayGenerationError(f"KB {kb_name!r} has no active generation")
        return int(meta.active_generation)

    if text == "shadow":
        if meta.shadow_generation is None:
            raise ReplayGenerationError(f"KB {kb_name!r} has no shadow generation")
        shadow = meta.get_shadow()
        if shadow is None or shadow.status != GenerationStatus.READY:
            raise ReplayGenerationError("shadow generation is not ready")
        return int(meta.shadow_generation)

    if text.startswith("g"):
        text = text[1:]
    try:
        generation = int(text)
    except ValueError as exc:
        raise ReplayGenerationError(f"invalid generation selector: {selector!r}") from exc
    if generation <= 0:
        raise ReplayGenerationError("generation must be positive")
    _assert_generation_available(kb_name, settings, generation)
    return generation


def load_generation_state(kb_name: str, settings: "Settings", generation: int) -> GraphState:
    """Load a generation into a temporary GraphState without touching AppState."""
    if settings.vector_store.provider == "qdrant":
        raise ReplayGenerationError("offline replay requires local NPZ vectors; qdrant-only replay is unsupported")
    _assert_generation_available(kb_name, settings, generation)
    paths = KbPaths(kb_name, settings, generation=generation)
    _require_file(paths.graph, "graph")
    _require_file(paths.vectors, "vectors")
    _require_file(paths.meta, "meta")

    graph = JsonGraphStore(paths.graph).load()
    node_ids = np.asarray(sorted(int(node_id) for node_id in graph.nodes), dtype=np.int64)
    _, vectors = NpzVectorStore(paths.vectors).load(node_ids)
    loaded_anchors, anchors_version = JsonAnchorStore(paths.anchors).load_with_version()
    anchors = {int(anchor.node_id): anchor for anchor in loaded_anchors if anchor.node_id is not None}
    meta = json.loads(paths.meta.read_text(encoding="utf-8"))
    build_id = str(meta.get("build_id") or meta.get("built_at") or "")
    if not build_id:
        root_meta = read_meta(paths.kb_root)
        entry = root_meta.generations.get(generation) if root_meta is not None else None
        if isinstance(entry, ReadyGeneration):
            build_id = entry.build_id
    meta = dict(meta)
    meta["served_by_generation"] = int(generation)
    return GraphState(
        graph=graph,
        vectors=vectors,
        anchors=anchors,
        kb_name=kb_name,
        meta=meta,
        build_id=build_id or f"g{generation}",
        anchors_version=anchors_version,
    )


def _assert_generation_available(kb_name: str, settings: "Settings", generation: int) -> None:
    kb_root = Path(settings.storage.data_dir) / kb_name
    meta = read_meta(kb_root)
    if meta is None:
        raise ReplayGenerationError(f"index.json not found for KB {kb_name!r}")
    entry = meta.generations.get(int(generation))
    if entry is None:
        raise ReplayGenerationError(f"generation g{generation} not found for KB {kb_name!r}")
    if isinstance(entry, ReadyGeneration):
        if entry.retired_at:
            raise ReplayGenerationError(f"generation g{generation} is retired")
        return
    if isinstance(entry, ShadowGeneration) and entry.status == GenerationStatus.READY:
        return
    raise ReplayGenerationError(f"generation g{generation} is not ready")


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ReplayGenerationError(f"missing {label} artifact: {path}")


__all__ = [
    "ReplayGenerationError",
    "load_generation_state",
    "resolve_generation_selector",
]
