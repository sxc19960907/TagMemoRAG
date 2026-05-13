from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .chunk_identity import ChunkIdentityMap, entry_from_chunk, entry_from_node, load_chunk_identity
from .config import Settings
from .errors import RebuildFailedError
from .graph_builder import build_graph
from .manual_library import ManualLibraryManifest, is_active_status, list_records
from .manuals import load_manual_metadata, metadata_from_node
from .observability.metrics import get_metrics
from .parser import parse_document
from .rebuild_impact import make_impact_report
from .storage.json_anchor import JsonAnchorStore
from .types import Chunk, GraphState


@dataclass(frozen=True)
class RebuildDetail:
    requested_mode: str = "full"
    effective_mode: str = "full"
    dirty_manual_count: int = 0
    fallback_reason: str = ""
    reused_chunk_count: int = 0
    embedded_chunk_count: int = 0
    auto_decision_reason: str = ""
    chunk_identity_fallback_reason: str = ""
    impact_report: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_mode": self.requested_mode,
            "effective_mode": self.effective_mode,
            "dirty_manual_count": self.dirty_manual_count,
            "fallback_reason": self.fallback_reason,
            "reused_chunk_count": self.reused_chunk_count,
            "embedded_chunk_count": self.embedded_chunk_count,
            "auto_decision_reason": self.auto_decision_reason,
            "chunk_identity_fallback_reason": self.chunk_identity_fallback_reason,
            "impact_report": self.impact_report,
        }


@dataclass(frozen=True)
class IncrementalBuildResult:
    state: GraphState | None
    detail: RebuildDetail


@dataclass(frozen=True)
class ReusableChunk:
    chunk: Chunk
    vector: np.ndarray


@dataclass
class IncrementalPlan:
    dirty_manual_ids: set[str]
    active_source_by_manual_id: dict[str, str]
    reusable: list[ReusableChunk] = field(default_factory=list)
    dirty_chunks: list[Chunk] = field(default_factory=list)
    chunk_identity_fallback_reason: str = ""


def build_kb_incremental(
    docs_dir: str | Path,
    kb_name: str,
    cfg: Settings,
    *,
    embedder,
    old_state: GraphState | None,
    manifest: ManualLibraryManifest,
    anchor_store: JsonAnchorStore,
    allow_fallback: bool = True,
    requested_mode: str = "incremental",
) -> IncrementalBuildResult:
    fallback_reason = _fallback_reason(docs_dir, old_state, manifest)
    dirty_count = len(manifest.dirty_manuals)
    if fallback_reason:
        if allow_fallback:
            return IncrementalBuildResult(None, RebuildDetail(requested_mode, "full", dirty_count, fallback_reason))
        raise RebuildFailedError({"fallback_reason": fallback_reason, "requested_mode": requested_mode})

    try:
        identity, identity_fallback_reason = load_chunk_identity(kb_name, cfg)
        plan = _build_plan(Path(docs_dir), kb_name, cfg, old_state, manifest, identity, identity_fallback_reason)
        dirty_vectors = _embed_dirty_chunks(plan.dirty_chunks, cfg, embedder)
        final_chunks, final_vectors = _assemble_final_inputs(plan, dirty_vectors, cfg.model.dim)
        graph = build_graph(final_chunks, final_vectors, cfg.graph)
        old_anchors, stored_anchor_version = anchor_store.load_with_version()
        by_key = {anchor.anchor_key: anchor for anchor in old_anchors}
        if old_state is not None:
            for anchor in old_state.anchors.values():
                by_key.setdefault(anchor.anchor_key, anchor)
        remapped, unresolved = anchor_store.reconcile(list(by_key.values()), graph, final_vectors, embedder)
        anchors = {anchor.node_id: anchor for anchor in remapped if anchor.node_id is not None}
        build_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        old_keys_by_manual = _identity_keys_by_manual_from_graph(old_state)
        new_keys_by_manual = _identity_keys_by_manual_from_chunks(final_chunks)
        old_identity_keys = {key for keys in old_keys_by_manual.values() for key in keys}
        new_identity_keys = {key for keys in new_keys_by_manual.values() for key in keys}
        embedded_identity_keys = {entry_from_chunk(chunk).identity_key for chunk in plan.dirty_chunks}
        reused_identity_keys = new_identity_keys - embedded_identity_keys
        impact_report = make_impact_report(
            kb_name=kb_name,
            build_id=build_id,
            manifest=manifest,
            old_identity_keys=old_identity_keys,
            new_identity_keys=new_identity_keys,
            reused_identity_keys=reused_identity_keys,
            embedded_identity_keys=embedded_identity_keys,
            old_keys_by_manual=old_keys_by_manual,
            new_keys_by_manual=new_keys_by_manual,
        )
        detail = RebuildDetail(
            requested_mode=requested_mode,
            effective_mode="incremental",
            dirty_manual_count=len(plan.dirty_manual_ids),
            reused_chunk_count=len(plan.reusable),
            embedded_chunk_count=len(plan.dirty_chunks),
            chunk_identity_fallback_reason=plan.chunk_identity_fallback_reason,
            impact_report=impact_report.to_dict(),
        )
        meta = {
            "schema_version": cfg.storage.schema_version,
            "model_name": getattr(embedder, "model_name", cfg.model.name),
            "model_dim": int(final_vectors.shape[1]) if final_vectors.ndim == 2 and final_vectors.shape[1] else cfg.model.dim,
            "built_at": _now(),
            "chunk_count": len(final_chunks),
            "aggregate_default": cfg.search.aggregate,
            "rebuild_mode": detail.effective_mode,
            "requested_mode": detail.requested_mode,
            "reused_chunk_count": detail.reused_chunk_count,
            "embedded_chunk_count": detail.embedded_chunk_count,
            "dirty_manual_count": detail.dirty_manual_count,
            "fallback_reason": detail.fallback_reason,
            "chunk_identity_fallback_reason": detail.chunk_identity_fallback_reason,
            "impact_report": impact_report.to_dict(),
            "impact_summary": impact_report.summary,
        }
        anchors_version = max(stored_anchor_version, old_state.anchors_version if old_state else 0)
        return IncrementalBuildResult(
            GraphState(
                graph=graph,
                vectors=final_vectors,
                anchors=anchors,
                build_id=build_id,
                kb_name=kb_name,
                meta=meta,
                unresolved_anchors=unresolved,
                anchors_version=anchors_version,
            ),
            detail,
        )
    except Exception:
        if allow_fallback:
            return IncrementalBuildResult(
                None,
                RebuildDetail(requested_mode, "full", dirty_count, "incremental_build_failed"),
            )
        raise


def _fallback_reason(docs_dir: str | Path, old_state: GraphState | None, manifest: ManualLibraryManifest) -> str:
    if old_state is None:
        return "missing_old_state"
    if not Path(docs_dir).exists():
        return "docs_dir_missing"
    if manifest.pending_changes and not manifest.dirty_manuals:
        return "missing_dirty_state"
    if not manifest.dirty_manuals:
        return "empty_dirty_state"
    if old_state.vectors.ndim != 2 or old_state.vectors.shape[0] != old_state.graph.number_of_nodes():
        return "vector_shape_mismatch"
    return ""


def _build_plan(
    docs_root: Path,
    kb_name: str,
    cfg: Settings,
    old_state: GraphState,
    manifest: ManualLibraryManifest,
    identity: ChunkIdentityMap | None,
    identity_fallback_reason: str,
) -> IncrementalPlan:
    records = {record.manual_id: record for record in list_records(kb_name, cfg)}
    dirty_manual_ids = set(manifest.dirty_manuals)
    active_source_by_manual_id: dict[str, str] = {}
    for manual_id, record in records.items():
        if record.exists and is_active_status(record.status):
            active_source_by_manual_id[manual_id] = record.source_file
    plan = IncrementalPlan(
        dirty_manual_ids=dirty_manual_ids,
        active_source_by_manual_id=active_source_by_manual_id,
        chunk_identity_fallback_reason=identity_fallback_reason,
    )
    old_node_ids = sorted(int(node_id) for node_id in old_state.graph.nodes)
    if old_node_ids and old_node_ids != list(range(len(old_node_ids))):
        raise RebuildFailedError({"fallback_reason": "non_contiguous_node_ids"})
    for node_id in old_node_ids:
        node = old_state.graph.nodes[node_id]
        metadata = metadata_from_node(node)
        manual_id = str(metadata.get("manual_id") or "")
        if not manual_id:
            raise RebuildFailedError({"fallback_reason": "missing_manual_id"})
        if manual_id in dirty_manual_ids or manual_id not in active_source_by_manual_id:
            continue
        source_file = str(node.get("source_file") or metadata.get("source_file") or "")
        if source_file != active_source_by_manual_id[manual_id]:
            raise RebuildFailedError({"fallback_reason": "source_file_mismatch", "manual_id": manual_id})
        plan.reusable.append(
            ReusableChunk(
                chunk=Chunk(
                    text=str(node.get("text") or ""),
                    header=str(node.get("header") or ""),
                    path=tuple(str(part) for part in node.get("path", [])) or ("",),
                    level=int(node.get("level") or 0),
                    start_line=int(node.get("start_line") or 1),
                    source_file=source_file,
                    metadata=metadata,
                ),
                vector=np.asarray(old_state.vectors[node_id], dtype=np.float32),
            )
        )
    seen_manual_ids = set()
    identity_entries = identity.chunks if identity is not None else {}
    used_dirty_identity_keys: set[str] = set()
    for source_file in sorted(active_source_by_manual_id[manual_id] for manual_id in dirty_manual_ids if manual_id in active_source_by_manual_id):
        path = docs_root / source_file
        metadata = load_manual_metadata(path, docs_root, seen_manual_ids=seen_manual_ids)
        if not is_active_status(metadata.status):
            continue
        for chunk in parse_document(
            path,
            cfg.parser.max_chars,
            cfg.parser.min_chars,
            root_dir=docs_root,
            metadata=metadata.to_node_attrs(),
        ):
            entry = entry_from_chunk(chunk)
            old_entry = identity_entries.get(entry.identity_key)
            if (
                old_entry is not None
                and old_entry.identity_key not in used_dirty_identity_keys
                and 0 <= old_entry.vector_row < old_state.vectors.shape[0]
            ):
                used_dirty_identity_keys.add(old_entry.identity_key)
                plan.reusable.append(
                    ReusableChunk(
                        chunk=chunk,
                        vector=np.asarray(old_state.vectors[old_entry.vector_row], dtype=np.float32),
                    )
                )
            else:
                plan.dirty_chunks.append(chunk)
    return plan


def _embed_dirty_chunks(chunks: list[Chunk], cfg: Settings, embedder) -> np.ndarray:
    if not chunks:
        return np.zeros((0, cfg.model.dim), dtype=np.float32)
    texts = [chunk.text for chunk in chunks]
    try:
        vectors = embedder.encode_batch(texts)
        get_metrics().record_embedding(operation="batch", outcome="success", duration=0.0)
        return np.asarray(vectors, dtype=np.float32)
    except Exception:
        get_metrics().record_embedding(operation="batch", outcome="error", duration=0.0)
        raise


def _assemble_final_inputs(plan: IncrementalPlan, dirty_vectors: np.ndarray, dim: int) -> tuple[list[Chunk], np.ndarray]:
    items: list[tuple[Chunk, np.ndarray]] = [(item.chunk, item.vector) for item in plan.reusable]
    items.extend((chunk, dirty_vectors[index]) for index, chunk in enumerate(plan.dirty_chunks))
    items.sort(key=lambda item: (item[0].source_file, item[0].start_line, item[0].header, item[0].text))
    chunks = [chunk for chunk, _vector in items]
    if not items:
        return [], np.zeros((0, dim), dtype=np.float32)
    vectors = np.asarray([vector for _chunk, vector in items], dtype=np.float32)
    return chunks, vectors


def _identity_keys_by_manual_from_graph(state: GraphState) -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {}
    for node_id, node in state.graph.nodes(data=True):
        entry = entry_from_node(int(node_id), node)
        if entry.manual_id:
            keys.setdefault(entry.manual_id, set()).add(entry.identity_key)
    return keys


def _identity_keys_by_manual_from_chunks(chunks: list[Chunk]) -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {}
    for chunk in chunks:
        entry = entry_from_chunk(chunk)
        if entry.manual_id:
            keys.setdefault(entry.manual_id, set()).add(entry.identity_key)
    return keys


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
