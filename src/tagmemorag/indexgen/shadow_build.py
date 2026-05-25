"""Shadow build entry — full-from-zero rebuild that writes to a generation directory.

Architecture v2 § A4 Decision D10: instead of teaching `build_kb_incremental`
to accept generation-aware paths, shadow build is a separate full-rebuild
function that targets ``KbPaths(kb, cfg, target_gen)`` for its core artifacts
(graph, vectors, chunk_identity, anchors, GraphState meta) and leaves
KB-shared global derivatives untouched (D11).

This module returns a ``GraphState`` for caller consumption (e.g. AppState's
shadow slot). It does NOT touch active reads, the index.json shadow slot,
or the rebuild task framework — those concerns live in ``state.py``'s
``start_shadow_rebuild`` (Slice 5 second half).
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Iterable, Mapping

import numpy as np
import structlog

from ..chunk_identity import build_chunk_identity_map, save_chunk_identity
from ..config import Settings
from ..document_assets import (
    AssetExtractionSummary,
    AssetManifest,
    asset_inventory_summary,
    extract_document_assets,
    load_asset_manifest,
    replace_document_assets,
)
from ..document_metadata import manual_node_attrs
from ..embedder import create_embedder
from ..errors import RebuildFailedError
from ..graph_builder import build_graph
from ..manual_library import is_active_status
from ..manuals import load_manual_metadata
from ..parser_provider import parse_chunks_for_config, supported_document_suffixes
from ..storage.json_anchor import JsonAnchorStore
from ..storage.json_graph import JsonGraphStore
from ..storage.npz_vector import NpzVectorStore
from ..storage.atomic import atomic_write
from ..types import GraphState
from .paths import KbPaths


_LOGGER = structlog.get_logger()


def _merge_asset_summary(left: AssetExtractionSummary, right: AssetExtractionSummary) -> AssetExtractionSummary:
    reasons = dict(left.failure_reasons)
    for reason, count in right.failure_reasons.items():
        reasons[reason] = reasons.get(reason, 0) + int(count)
    return AssetExtractionSummary(
        attempted=left.attempted + right.attempted,
        created=left.created + right.created,
        skipped=left.skipped + right.skipped,
        failed=left.failed + right.failed,
        failure_reasons=reasons,
    )


def _now_iso_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")


def _apply_target_versions(cfg: Settings, target_versions: Mapping[str, str | int] | None) -> Settings:
    """Return a deep-copied Settings with target_versions overlaid.

    Recognised keys (all optional):
      - parser_version  → cfg.parser.pdf_profile (proxy; parser version isn't yet a first-class field)
      - chunker_version → cfg.parser.overlap_chars (placeholder; chunker version not first-class either)
      - embedding_model_id → cfg.model.embedding_model_id
      - embedding_model_version → cfg.model.embedding_model_version
      - index_schema_version → cfg.storage.schema_version

    Unknown keys are silently ignored. Missing keys leave Settings unchanged.
    The deep-copy guarantees the original (active) Settings instance is not
    mutated.
    """
    overlay = deepcopy(cfg)
    if not target_versions:
        return overlay

    if "embedding_model_id" in target_versions:
        overlay.model.embedding_model_id = str(target_versions["embedding_model_id"])
    if "embedding_model_version" in target_versions:
        overlay.model.embedding_model_version = str(target_versions["embedding_model_version"])
    if "index_schema_version" in target_versions:
        overlay.storage.schema_version = str(target_versions["index_schema_version"])
    # parser_version / chunker_version: noted but not first-class fields yet.
    return overlay


def _save_meta_at(path: Path, meta: dict) -> None:
    import json

    def write(tmp_path: Path) -> None:
        tmp_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    atomic_write(path, write)


def build_shadow_kb(
    docs_dir: str | Path,
    kb_name: str,
    active_cfg: Settings,
    *,
    paths: KbPaths,
    target_versions: Mapping[str, str | int] | None = None,
    embedder=None,
    progress_cb=None,
) -> GraphState:
    """Run a full-from-zero KB build into ``paths.generation_root``.

    Parameters
    ----------
    docs_dir
        Source documents directory (same convention as ``build_kb``).
    kb_name
        KB this shadow targets.
    active_cfg
        Current (active) Settings. NOT mutated; an overlay copy is made via
        ``_apply_target_versions``.
    paths
        ``KbPaths`` instance specifying where products should be written.
        Caller is responsible for setting ``generation`` on the paths object;
        passing a legacy KbPaths (generation=None) effectively builds at
        kb_root and matches the existing ``build_kb`` location.
    target_versions
        Optional overlay. See ``_apply_target_versions`` for recognised keys.
    embedder
        Optional pre-instantiated embedder. If None, a fresh one is built
        from the overlaid Settings.
    progress_cb
        Optional ``Callable[[float, str], None]`` invoked with (progress 0..1,
        stage_name). Useful for streaming index.json progress. May be called
        from the build thread; must be cheap.
    """
    docs_root = Path(docs_dir)
    if not docs_root.exists():
        raise RebuildFailedError({"reason": "docs_dir does not exist", "docs_dir": str(docs_root)})

    cfg = _apply_target_versions(active_cfg, target_versions)

    if progress_cb:
        progress_cb(0.0, "init")

    if embedder is None:
        embedder = create_embedder(
            cfg.model.name,
            cfg.model.device,
            cfg.model.batch_size,
            cfg.model.dim,
            provider=cfg.model.provider,
            base_url=cfg.model.base_url,
            embeddings_url=cfg.model.embeddings_url,
            api_key_env=cfg.model.api_key_env,
            timeout_seconds=cfg.model.timeout_seconds,
            dimensions=cfg.model.dimensions,
            normalize=cfg.model.normalize,
        )

    chunks = []
    asset_manifest = (
        load_asset_manifest(kb_name, cfg) if cfg.assets.enabled else AssetManifest(kb_name=kb_name)
    )
    asset_summary = AssetExtractionSummary()
    supported_suffixes = supported_document_suffixes(cfg.parser)
    document_paths: Iterable[Path] = (p for p in docs_root.rglob("*") if p.is_file() and p.suffix.lower() in supported_suffixes)
    seen_manual_ids: set[str] = set()

    paths.ensure_generation_root()

    if progress_cb:
        progress_cb(0.05, "parse")

    for path in sorted(document_paths):
        metadata = load_manual_metadata(path, docs_root, seen_manual_ids=seen_manual_ids)
        if not is_active_status(metadata.status):
            continue
        chunks.extend(
            parse_chunks_for_config(
                path,
                cfg.parser,
                root_dir=docs_root,
                metadata=manual_node_attrs(metadata),
            )
        )
        if cfg.assets.enabled:
            document_assets, document_asset_summary = extract_document_assets(path, metadata, kb_name, cfg)
            asset_manifest = replace_document_assets(asset_manifest, metadata.manual_id, document_assets)
            asset_summary = _merge_asset_summary(asset_summary, document_asset_summary)

    texts = [chunk.text for chunk in chunks]

    if progress_cb:
        progress_cb(0.2, "embed")

    emb_t0 = time.perf_counter()
    if texts:
        vectors = embedder.encode_batch(texts)
    else:
        vectors = np.zeros((0, cfg.model.dim), dtype=np.float32)
    emb_duration = time.perf_counter() - emb_t0
    _LOGGER.info(
        "shadow_build_embed",
        kb_name=kb_name,
        chunk_count=len(chunks),
        embedder_id=cfg.model.effective_embedding_model_id,
        embedder_version=cfg.model.embedding_model_version,
        duration_seconds=round(emb_duration, 3),
    )

    if progress_cb:
        progress_cb(0.6, "graph")

    graph = build_graph(chunks, vectors, cfg.graph)
    build_id = _now_iso_compact()

    if progress_cb:
        progress_cb(0.75, "anchor_reconcile")

    anchor_store = JsonAnchorStore(paths.anchors)
    remapped, unresolved = anchor_store.reconcile([], graph, vectors, embedder)
    anchors = {anchor.node_id: anchor for anchor in remapped if anchor.node_id is not None}
    anchors_version = 0

    state_meta = {
        "schema_version": cfg.storage.schema_version,
        "model_name": getattr(embedder, "model_name", cfg.model.name),
        "model_dim": int(vectors.shape[1]) if vectors.ndim == 2 and vectors.shape[1] else cfg.model.dim,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "chunk_count": len(chunks),
        "aggregate_default": cfg.search.aggregate,
        "shadow_build": True,
        "embedding_model_id": cfg.model.effective_embedding_model_id,
        "embedding_model_version": cfg.model.embedding_model_version,
    }
    if cfg.assets.enabled:
        state_meta["assets"] = asset_inventory_summary(asset_manifest, asset_summary)

    if progress_cb:
        progress_cb(0.85, "save")

    JsonGraphStore(paths.graph).save(graph)
    JsonAnchorStore(paths.anchors).save(list(anchors.values()), version=anchors_version)
    NpzVectorStore(paths.vectors).add(np.arange(vectors.shape[0]), vectors)
    save_chunk_identity(
        paths.chunk_identity,
        build_chunk_identity_map(graph, kb_name=kb_name, build_id=build_id, cfg=cfg),
    )
    _save_meta_at(paths.meta, state_meta)

    if progress_cb:
        progress_cb(1.0, "done")

    return GraphState(
        graph=graph,
        vectors=vectors,
        anchors=anchors,
        build_id=build_id,
        kb_name=kb_name,
        meta=state_meta,
        asset_manifest=asset_manifest if cfg.assets.enabled else None,
        unresolved_anchors=unresolved,
        anchors_version=anchors_version,
    )
