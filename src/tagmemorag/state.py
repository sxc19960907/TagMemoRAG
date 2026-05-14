from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import threading
import time
import uuid

import numpy as np
import structlog

from .chunk_identity import build_chunk_identity_map, entry_from_node, identity_path, load_chunk_identity, save_chunk_identity
from .config import Settings
from .embedder import create_embedder
from .errors import KbNotLoadedError, RebuildFailedError, RebuildInProgressError, ShuttingDownError, StorageSchemaMismatchError
from .graph_builder import build_graph
from .incremental_rebuild import RebuildDetail, build_kb_incremental
from .manual_library import clear_pending_after_success, is_active_status, load_manifest
from .manuals import load_manual_metadata
from .observability.metrics import get_metrics
from .observability.tracing import set_span_attributes, start_span
from .parser import SUPPORTED_DOCUMENT_SUFFIXES, parse_document
from .rebuild_impact import ManualImpact, RebuildImpactReport, impact_path, make_impact_report, save_rebuild_impact
from .storage.atomic import atomic_write
from .storage.json_anchor import JsonAnchorStore
from .storage.json_graph import JsonGraphStore
from .storage.npz_vector import NpzVectorStore
from .storage.qdrant_vector import QdrantVectorStore
from .types import Anchor, GraphState


@dataclass
class RebuildTask:
    task_id: str
    status: str
    kb_name: str
    started_at: str
    finished_at: str | None = None
    error: dict | None = None
    build_id: str | None = None
    requested_mode: str = "full"
    effective_mode: str = "full"
    dirty_manual_count: int = 0
    fallback_reason: str = ""
    reused_chunk_count: int = 0
    embedded_chunk_count: int = 0
    auto_decision_reason: str = ""
    chunk_identity_fallback_reason: str = ""
    impact_report: dict | None = None
    qdrant_sync: dict | None = None

    def to_dict(self) -> dict:
        data = {
            "task_id": self.task_id,
            "status": self.status,
            "kb_name": self.kb_name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "build_id": self.build_id,
            "requested_mode": self.requested_mode,
            "effective_mode": self.effective_mode,
            "dirty_manual_count": self.dirty_manual_count,
            "fallback_reason": self.fallback_reason,
            "reused_chunk_count": self.reused_chunk_count,
            "embedded_chunk_count": self.embedded_chunk_count,
            "auto_decision_reason": self.auto_decision_reason,
            "chunk_identity_fallback_reason": self.chunk_identity_fallback_reason,
            "impact_report": self.impact_report,
            "impact_summary": self.impact_report.get("summary") if isinstance(self.impact_report, dict) else None,
            "qdrant_sync": self.qdrant_sync,
        }
        summary = getattr(self, "operations_summary", None)
        if callable(summary):
            data["operations_summary"] = summary()
        return data


@dataclass
class AppState:
    current: GraphState | None = None
    kbs: dict[str, GraphState] = field(default_factory=dict)
    rebuild_locks: dict[str, threading.Lock] = field(default_factory=dict)
    rebuild_tasks: dict[str, RebuildTask] = field(default_factory=dict)
    embedder_ready: bool = False
    is_shutting_down: bool = False
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _rebuild_lock: threading.Lock = field(default_factory=threading.Lock)
    auth_store: object | None = None
    rate_limiter: object | None = None
    query_cache: object | None = None

    def __post_init__(self) -> None:
        self.rebuild_locks.setdefault("default", self._rebuild_lock)
        if self.current is not None:
            self.kbs[self.current.kb_name] = self.current

    def get_current(self, kb_name: str = "default") -> GraphState:
        return self.get_kb(kb_name)

    def get_kb(self, kb_name: str = "default") -> GraphState:
        with self._lock:
            state = self.kbs.get(kb_name)
            if state is None:
                raise KbNotLoadedError(kb_name)
            return state

    def swap(self, new_state: GraphState) -> None:
        self.swap_kb(new_state.kb_name, new_state)

    def swap_kb(self, kb_name: str, new_state: GraphState) -> None:
        with self._lock:
            self.kbs[kb_name] = new_state
            if kb_name == "default" or self.current is None or self.current.kb_name == kb_name:
                self.current = new_state

    def list_kbs(self) -> list[str]:
        with self._lock:
            return sorted(self.kbs)

    def lock_for(self, kb_name: str) -> threading.Lock:
        with self._lock:
            lock = self.rebuild_locks.get(kb_name)
            if lock is None:
                lock = threading.Lock()
                self.rebuild_locks[kb_name] = lock
            return lock

    def mark_embedder_ready(self) -> None:
        with self._lock:
            self.embedder_ready = True

    def begin_shutdown(self) -> None:
        with self._lock:
            self.is_shutting_down = True

    def start_rebuild(
        self,
        docs_dir: str | Path,
        kb_name: str,
        cfg: Settings,
        embedder=None,
        on_success=None,
        mode: str = "full",
        allow_fallback: bool = True,
        is_library_rebuild: bool = False,
        cleanup=None,
    ) -> RebuildTask:
        with self._lock:
            if self.is_shutting_down:
                get_metrics().record_rebuild_rejected(kb_name=kb_name)
                raise ShuttingDownError()
        rebuild_lock = self.lock_for(kb_name)
        if not rebuild_lock.acquire(blocking=False):
            running = next(
                (task.task_id for task in self.rebuild_tasks.values() if task.status == "running" and task.kb_name == kb_name),
                None,
            )
            get_metrics().record_rebuild_rejected(kb_name=kb_name)
            raise RebuildInProgressError(running)
        task_id = str(uuid.uuid4())
        task = RebuildTask(
            task_id=task_id,
            status="running",
            kb_name=kb_name,
            started_at=_now(),
            requested_mode=mode,
            effective_mode="full" if mode == "full" else mode,
        )
        self.rebuild_tasks[task_id] = task
        get_metrics().record_rebuild_started(kb_name=kb_name)
        get_metrics().set_rebuild_in_progress(kb_name=kb_name, value=1)
        structlog.get_logger().info(
            "rebuild_started",
            task_id=task_id,
            docs_dir=str(docs_dir),
            kb_name=kb_name,
            requested_mode=mode,
        )
        thread = threading.Thread(
            target=self._rebuild_worker,
            args=(task, docs_dir, kb_name, cfg, embedder, rebuild_lock, on_success, mode, allow_fallback, is_library_rebuild, cleanup),
            daemon=True,
        )
        thread.start()
        return task

    def _rebuild_worker(
        self,
        task: RebuildTask,
        docs_dir: str | Path,
        kb_name: str,
        cfg: Settings,
        embedder,
        rebuild_lock: threading.Lock,
        on_success,
        mode: str,
        allow_fallback: bool,
        is_library_rebuild: bool,
        cleanup,
    ) -> None:
        t0 = time.perf_counter()
        try:
            old_state = self.kbs.get(kb_name)
            with start_span(
                "tagmemorag.rebuild",
                **{"tagmemorag.kb_name": kb_name, "tagmemorag.x_trace_id": task.task_id},
            ):
                new_state = _build_for_rebuild(
                    docs_dir,
                    kb_name,
                    cfg,
                    embedder=embedder,
                    old_state=old_state,
                    mode=mode,
                    allow_fallback=allow_fallback,
                    is_library_rebuild=is_library_rebuild,
                    task=task,
                )
                if is_library_rebuild and cfg.vector_store.provider == "qdrant":
                    qdrant_sync = sync_qdrant_for_rebuild(new_state, old_state, cfg, task)
                    task.qdrant_sync = qdrant_sync.to_dict()
                    new_state.meta["qdrant_sync"] = task.qdrant_sync
                    if isinstance(task.impact_report, dict):
                        task.impact_report["qdrant_sync"] = task.qdrant_sync
                    _save_kb_metadata_artifacts(new_state, cfg)
                else:
                    save_kb(new_state, cfg)
                if is_library_rebuild and task.status != "failed":
                    save_chunk_identity(identity_path(kb_name, cfg), build_chunk_identity_map(new_state.graph, kb_name=kb_name, build_id=new_state.build_id, cfg=cfg))
                    if isinstance(task.impact_report, dict):
                        manuals = [ManualImpact(**item) for item in task.impact_report.get("manuals", []) if isinstance(item, dict)]
                        save_rebuild_impact(
                            impact_path(kb_name, cfg.storage.data_dir),
                            RebuildImpactReport(
                                kb_name=str(task.impact_report.get("kb_name") or kb_name),
                                build_id=str(task.impact_report.get("build_id") or new_state.build_id),
                                summary=dict(task.impact_report.get("summary") or {}),
                                manuals=manuals,
                                qdrant_sync=task.qdrant_sync,
                            ),
                        )
                self.swap_kb(kb_name, new_state)
                if self.query_cache is not None:
                    self.query_cache.clear(kb_name)
                if on_success is not None:
                    on_success(new_state)
                task.status = "done"
                task.build_id = new_state.build_id
                set_span_attributes(
                    **{
                        "tagmemorag.build_id": new_state.build_id,
                        "tagmemorag.rebuild.task_status": task.status,
                    }
                )
                get_metrics().record_rebuild_done(kb_name=kb_name, duration=time.perf_counter() - t0)
                get_metrics().set_kbs_loaded(len(self.kbs))
                structlog.get_logger().info(
                    "rebuild_done",
                    task_id=task.task_id,
                    kb_name=kb_name,
                    build_id=new_state.build_id,
                    duration_ms=round((time.perf_counter() - t0) * 1000.0, 3),
                    chunk_count=new_state.graph.number_of_nodes(),
                    requested_mode=task.requested_mode,
                    effective_mode=task.effective_mode,
                    dirty_manual_count=task.dirty_manual_count,
                    fallback_reason=task.fallback_reason,
                )
        except Exception as exc:
            task.status = "failed"
            task.error = {"type": type(exc).__name__, "message": str(exc)}
            get_metrics().record_rebuild_failed(kb_name=kb_name, duration=time.perf_counter() - t0)
            structlog.get_logger().error(
                "rebuild_failed",
                task_id=task.task_id,
                kb_name=kb_name,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        finally:
            task.finished_at = _now()
            get_metrics().set_rebuild_in_progress(kb_name=kb_name, value=0)
            if cleanup is not None:
                cleanup()
            rebuild_lock.release()


def build_kb(docs_dir: str | Path, kb_name: str, cfg: Settings, embedder=None, old_state: GraphState | None = None) -> GraphState:
    with start_span("tagmemorag.kb.build", **{"tagmemorag.kb_name": kb_name}):
        docs_root = Path(docs_dir)
        if not docs_root.exists():
            raise RebuildFailedError({"reason": "docs_dir does not exist", "docs_dir": str(docs_root)})
        embedder = embedder or create_embedder(
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
        document_paths = (
            p for p in docs_root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_DOCUMENT_SUFFIXES
        )
        seen_manual_ids: set[str] = set()
        for path in sorted(document_paths):
            metadata = load_manual_metadata(path, docs_root, seen_manual_ids=seen_manual_ids)
            if not is_active_status(metadata.status):
                continue
            chunks.extend(
                parse_document(
                    path,
                    cfg.parser.max_chars,
                    cfg.parser.min_chars,
                    root_dir=docs_root,
                    metadata=metadata.to_node_attrs(),
                )
            )
        texts = [chunk.text for chunk in chunks]
        emb_t0 = time.perf_counter()
        try:
            vectors = embedder.encode_batch(texts) if texts else np.zeros((0, cfg.model.dim), dtype=np.float32)
            get_metrics().record_embedding(operation="batch", outcome="success", duration=time.perf_counter() - emb_t0)
        except Exception:
            get_metrics().record_embedding(operation="batch", outcome="error", duration=time.perf_counter() - emb_t0)
            raise
        graph = build_graph(chunks, vectors, cfg.graph)
        anchor_store = _anchor_store(kb_name, cfg)
        old_anchors, stored_anchor_version = anchor_store.load_with_version()
        if old_state:
            by_key = {anchor.anchor_key: anchor for anchor in old_anchors}
            for anchor in old_state.anchors.values():
                by_key.setdefault(anchor.anchor_key, anchor)
            old_anchors = list(by_key.values())
        remapped, unresolved = anchor_store.reconcile(old_anchors, graph, vectors, embedder)
        anchors = {anchor.node_id: anchor for anchor in remapped if anchor.node_id is not None}
        build_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        meta = {
            "schema_version": cfg.storage.schema_version,
            "model_name": getattr(embedder, "model_name", cfg.model.name),
            "model_dim": int(vectors.shape[1]) if vectors.ndim == 2 and vectors.shape[1] else cfg.model.dim,
            "built_at": _now(),
            "chunk_count": len(chunks),
            "aggregate_default": cfg.search.aggregate,
        }
        anchors_version = max(stored_anchor_version, old_state.anchors_version if old_state else 0)
        set_span_attributes(**{"tagmemorag.build_id": build_id, "tagmemorag.result_count": len(chunks)})
        return GraphState(
            graph=graph,
            vectors=vectors,
            anchors=anchors,
            build_id=build_id,
            kb_name=kb_name,
            meta=meta,
            unresolved_anchors=unresolved,
            anchors_version=anchors_version,
        )


def _build_for_rebuild(
    docs_dir: str | Path,
    kb_name: str,
    cfg: Settings,
    *,
    embedder,
    old_state: GraphState | None,
    mode: str,
    allow_fallback: bool,
    is_library_rebuild: bool,
    task: RebuildTask,
) -> GraphState:
    requested_mode = mode if mode in {"full", "incremental", "auto"} else "full"
    embedder = embedder or create_embedder(
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
    manifest = load_manifest(kb_name, cfg) if is_library_rebuild else None
    auto_decision_reason = ""
    if is_library_rebuild and requested_mode == "auto" and manifest is not None:
        effective_attempt, auto_decision_reason = _auto_incremental_decision(docs_dir, kb_name, cfg, manifest)
        task.auto_decision_reason = auto_decision_reason
    else:
        effective_attempt = requested_mode == "incremental"
    attempt_incremental = is_library_rebuild and effective_attempt
    if attempt_incremental and manifest is not None:
        result = build_kb_incremental(
            docs_dir,
            kb_name,
            cfg,
            embedder=embedder,
            old_state=old_state,
            manifest=manifest,
            anchor_store=_anchor_store(kb_name, cfg),
            allow_fallback=allow_fallback,
            requested_mode=requested_mode,
        )
        detail = RebuildDetail(
            requested_mode=result.detail.requested_mode,
            effective_mode=result.detail.effective_mode,
            dirty_manual_count=result.detail.dirty_manual_count,
            fallback_reason=result.detail.fallback_reason,
            reused_chunk_count=result.detail.reused_chunk_count,
            embedded_chunk_count=result.detail.embedded_chunk_count,
            auto_decision_reason=auto_decision_reason,
            chunk_identity_fallback_reason=result.detail.chunk_identity_fallback_reason,
            impact_report=result.detail.impact_report,
        )
        _apply_rebuild_detail(task, detail)
        if result.state is not None:
            set_span_attributes(
                **{
                    "tagmemorag.build_id": result.state.build_id,
                    "tagmemorag.result_count": result.state.graph.number_of_nodes(),
                }
            )
            return result.state
    new_state = build_kb(docs_dir, kb_name, cfg, embedder=embedder, old_state=old_state)
    fallback_reason = task.fallback_reason
    dirty_count = len(manifest.dirty_manuals) if manifest is not None else 0
    impact_report = _full_rebuild_impact(kb_name, new_state, old_state, manifest)
    detail = RebuildDetail(
        requested_mode=requested_mode,
        effective_mode="full",
        dirty_manual_count=dirty_count,
        fallback_reason=fallback_reason,
        embedded_chunk_count=new_state.graph.number_of_nodes(),
        auto_decision_reason=auto_decision_reason,
        impact_report=impact_report,
    )
    new_state.meta.update(
        {
            "rebuild_mode": detail.effective_mode,
            "requested_mode": detail.requested_mode,
            "reused_chunk_count": detail.reused_chunk_count,
            "embedded_chunk_count": detail.embedded_chunk_count,
            "dirty_manual_count": detail.dirty_manual_count,
            "fallback_reason": detail.fallback_reason,
            "auto_decision_reason": detail.auto_decision_reason,
            "impact_report": impact_report,
            "impact_summary": impact_report.get("summary") if isinstance(impact_report, dict) else None,
        }
    )
    _apply_rebuild_detail(task, detail)
    return new_state


def _apply_rebuild_detail(task: RebuildTask, detail: RebuildDetail) -> None:
    task.requested_mode = detail.requested_mode
    task.effective_mode = detail.effective_mode
    task.dirty_manual_count = detail.dirty_manual_count
    task.fallback_reason = detail.fallback_reason
    task.reused_chunk_count = detail.reused_chunk_count
    task.embedded_chunk_count = detail.embedded_chunk_count
    task.auto_decision_reason = detail.auto_decision_reason
    task.chunk_identity_fallback_reason = detail.chunk_identity_fallback_reason
    task.impact_report = detail.impact_report


def _auto_incremental_decision(docs_dir: str | Path, kb_name: str, cfg: Settings, manifest) -> tuple[bool, str]:
    dirty_manual_count = len(manifest.dirty_manuals)
    if manifest.pending_changes and not manifest.dirty_manuals:
        return False, "missing_dirty_state"
    if not manifest.dirty_manuals:
        return False, "empty_dirty_state"
    if dirty_manual_count > cfg.manual_library.incremental_auto_max_dirty_manuals:
        return False, "auto_dirty_manual_threshold_exceeded"
    dirty_chunk_estimate = _estimate_dirty_chunks(docs_dir, kb_name, cfg, manifest)
    if dirty_chunk_estimate > cfg.manual_library.incremental_auto_max_dirty_chunks:
        return False, "auto_dirty_chunk_threshold_exceeded"
    return True, "auto_thresholds_within_limit"


def _estimate_dirty_chunks(docs_dir: str | Path, kb_name: str, cfg: Settings, manifest) -> int:
    docs_root = Path(docs_dir)
    total = 0
    seen_manual_ids: set[str] = set()
    for dirty in manifest.dirty_manuals.values():
        if dirty.operation in {"disable", "archive", "hard_delete"} or not dirty.source_file:
            continue
        path = docs_root / dirty.source_file
        if not path.exists():
            continue
        metadata = load_manual_metadata(path, docs_root, seen_manual_ids=seen_manual_ids)
        if not is_active_status(metadata.status):
            continue
        total += len(parse_document(path, cfg.parser.max_chars, cfg.parser.min_chars, root_dir=docs_root, metadata=metadata.to_node_attrs()))
    return total


def _full_rebuild_impact(kb_name: str, new_state: GraphState, old_state: GraphState | None, manifest) -> dict:
    old_keys_by_manual: dict[str, set[str]] = {}
    if old_state is not None:
        for node_id, node in old_state.graph.nodes(data=True):
            entry = entry_from_node(int(node_id), node)
            if entry.manual_id:
                old_keys_by_manual.setdefault(entry.manual_id, set()).add(entry.identity_key)
    new_keys_by_manual: dict[str, set[str]] = {}
    for node_id, node in new_state.graph.nodes(data=True):
        entry = entry_from_node(int(node_id), node)
        if entry.manual_id:
            new_keys_by_manual.setdefault(entry.manual_id, set()).add(entry.identity_key)
    old_identity_keys = {key for keys in old_keys_by_manual.values() for key in keys}
    new_identity_keys = {key for keys in new_keys_by_manual.values() for key in keys}
    report = make_impact_report(
        kb_name=kb_name,
        build_id=new_state.build_id,
        manifest=manifest,
        old_identity_keys=old_identity_keys,
        new_identity_keys=new_identity_keys,
        reused_identity_keys=set(),
        embedded_identity_keys=new_identity_keys,
        old_keys_by_manual=old_keys_by_manual,
        new_keys_by_manual=new_keys_by_manual,
    )
    return report.to_dict()


def save_kb(state: GraphState, cfg: Settings) -> None:
    root = _kb_dir(state.kb_name, cfg)
    JsonGraphStore(root / "graph.json").save(state.graph)
    vector_store = _vector_store(state.kb_name, cfg, dim=_vector_dim(state))
    ids = np.arange(state.vectors.shape[0])
    if cfg.vector_store.provider == "qdrant":
        vector_store.add(ids, state.vectors, payloads=_qdrant_payloads(state, cfg))
    else:
        vector_store.add(ids, state.vectors)
    JsonAnchorStore(root / "anchors.json").save(list(state.anchors.values()), version=state.anchors_version)
    _save_meta(root, state.meta)


def _save_kb_metadata_artifacts(state: GraphState, cfg: Settings) -> None:
    root = _kb_dir(state.kb_name, cfg)
    JsonGraphStore(root / "graph.json").save(state.graph)
    JsonAnchorStore(root / "anchors.json").save(list(state.anchors.values()), version=state.anchors_version)
    _save_meta(root, state.meta)


def _save_meta(root: Path, meta: dict) -> None:
    def write_meta(tmp_path: Path) -> None:
        tmp_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    atomic_write(root / "meta.json", write_meta)


def load_kb(kb_name: str, cfg: Settings) -> GraphState:
    root = _kb_dir(kb_name, cfg)
    meta_path = root / "meta.json"
    if not meta_path.exists():
        raise KbNotLoadedError(kb_name)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if str(meta.get("schema_version")) != cfg.storage.schema_version:
        raise StorageSchemaMismatchError(cfg.storage.schema_version, meta.get("schema_version"))
    graph = JsonGraphStore(root / "graph.json").load()
    node_ids = np.asarray(sorted(int(node_id) for node_id in graph.nodes), dtype=np.int64)
    _, vectors = _vector_store(kb_name, cfg, dim=int(meta.get("model_dim") or cfg.model.dim)).load(node_ids)
    loaded, anchors_version = JsonAnchorStore(root / "anchors.json").load_with_version()
    anchors = {anchor.node_id: anchor for anchor in loaded if anchor.node_id is not None}
    return GraphState(
        graph=graph,
        vectors=vectors,
        anchors=anchors,
        kb_name=kb_name,
        meta=meta,
        build_id=str(meta.get("built_at", _now())),
        anchors_version=anchors_version,
    )


def _kb_dir(kb_name: str, cfg: Settings) -> Path:
    return Path(cfg.storage.data_dir) / kb_name


def _anchor_store(kb_name: str, cfg: Settings) -> JsonAnchorStore:
    return JsonAnchorStore(_kb_dir(kb_name, cfg) / "anchors.json")


def _vector_store(kb_name: str, cfg: Settings, *, dim: int):
    if cfg.vector_store.provider == "qdrant":
        return QdrantVectorStore(
            kb_name=kb_name,
            dim=dim,
            url=cfg.vector_store.qdrant_url,
            collection_prefix=cfg.vector_store.collection_prefix,
            timeout_seconds=cfg.vector_store.timeout_seconds,
        )
    return NpzVectorStore(_kb_dir(kb_name, cfg) / "vectors.npz")


def _vector_dim(state: GraphState) -> int:
    if state.vectors.ndim == 2 and state.vectors.shape[1]:
        return int(state.vectors.shape[1])
    return int(state.meta.get("model_dim") or 0)


@dataclass(frozen=True)
class QdrantSyncSummary:
    provider: str = "qdrant"
    strategy: str = "skipped"
    points_upserted: int = 0
    points_deleted: int = 0
    points_reused: int = 0
    fallback_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "strategy": self.strategy,
            "points_upserted": self.points_upserted,
            "points_deleted": self.points_deleted,
            "points_reused": self.points_reused,
            "fallback_reason": self.fallback_reason,
        }


def sync_qdrant_for_rebuild(
    new_state: GraphState,
    old_state: GraphState | None,
    cfg: Settings,
    task: RebuildTask | None = None,
) -> QdrantSyncSummary:
    vector_store = _vector_store(new_state.kb_name, cfg, dim=_vector_dim(new_state))
    new_ids = np.arange(new_state.vectors.shape[0], dtype=np.int64)
    old_ids = _state_node_ids(old_state)
    stale_ids = sorted(old_ids - {int(node_id) for node_id in new_ids})
    reusable_node_ids, fallback_reason = _qdrant_reusable_node_ids(new_state, old_state, cfg, task)
    if fallback_reason:
        upsert_ids = new_ids
        strategy = "full_sync"
        reused_count = 0
    else:
        upsert_ids = np.asarray([int(node_id) for node_id in new_ids if int(node_id) not in reusable_node_ids], dtype=np.int64)
        strategy = "point_incremental"
        reused_count = len(reusable_node_ids)

    vector_store.update(upsert_ids, new_state.vectors[upsert_ids] if len(upsert_ids) else np.zeros((0, _vector_dim(new_state)), dtype=np.float32), payloads=_qdrant_payloads(new_state, cfg, upsert_ids))
    if strategy == "point_incremental" and reusable_node_ids:
        reused_ids = np.asarray(sorted(reusable_node_ids), dtype=np.int64)
        vector_store.update_payloads(reused_ids, _qdrant_payloads(new_state, cfg, reused_ids))
    vector_store.delete(stale_ids)
    return QdrantSyncSummary(
        strategy=strategy,
        points_upserted=len(upsert_ids),
        points_deleted=len(stale_ids),
        points_reused=reused_count,
        fallback_reason=fallback_reason,
    )


def _state_node_ids(state: GraphState | None) -> set[int]:
    if state is None:
        return set()
    return {int(node_id) for node_id in state.graph.nodes}


def _qdrant_reusable_node_ids(
    new_state: GraphState,
    old_state: GraphState | None,
    cfg: Settings,
    task: RebuildTask | None,
) -> tuple[set[int], str]:
    if old_state is None:
        return set(), "missing_old_state"
    if task is None or task.effective_mode != "incremental":
        return set(), "not_incremental_rebuild"
    old_identity, reason = load_chunk_identity(new_state.kb_name, cfg)
    if old_identity is None:
        return set(), reason or "missing_chunk_identity"
    if task.chunk_identity_fallback_reason:
        return set(), task.chunk_identity_fallback_reason
    old_by_key = old_identity.chunks
    reusable: set[int] = set()
    for node_id, node in new_state.graph.nodes(data=True):
        entry = entry_from_node(int(node_id), node)
        old_entry = old_by_key.get(entry.identity_key)
        if old_entry is None:
            continue
        if old_entry.text_hash != entry.text_hash or old_entry.metadata_hash != entry.metadata_hash:
            continue
        if int(old_entry.node_id) != int(node_id):
            return set(), "node_id_reassigned"
        if int(node_id) not in old_state.graph:
            return set(), "old_node_missing"
        reusable.add(int(node_id))
    if len(reusable) > new_state.graph.number_of_nodes():
        return set(), "ambiguous_chunk_identity"
    return reusable, ""


def _qdrant_payloads(state: GraphState, cfg: Settings, ids: np.ndarray | list[int] | None = None) -> list[dict[str, Any]]:
    identity = build_chunk_identity_map(state.graph, kb_name=state.kb_name, build_id=state.build_id, cfg=cfg)
    selected_ids = [int(node_id) for node_id in (ids if ids is not None else np.arange(state.vectors.shape[0]))]
    payloads: list[dict[str, Any]] = []
    by_node_id = {entry.node_id: entry for entry in identity.chunks.values()}
    for node_id in selected_ids:
        entry = by_node_id.get(node_id)
        node = state.graph.nodes[node_id] if node_id in state.graph else {}
        payloads.append(
            {
                "kb_name": state.kb_name,
                "node_id": node_id,
                "build_id": state.build_id,
                "chunk_identity_key": entry.identity_key if entry is not None else "",
                "manual_id": entry.manual_id if entry is not None else str(node.get("manual_id") or ""),
                "source_file": entry.source_file if entry is not None else str(node.get("source_file") or ""),
                "text_hash": entry.text_hash if entry is not None else "",
            }
        )
    return payloads


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def start_library_rebuild(
    app_state: AppState,
    kb_name: str,
    cfg: Settings,
    embedder=None,
    *,
    mode: str = "full",
    allow_fallback: bool = True,
) -> RebuildTask:
    from .manual_library import library_root, materialize_registry_build_source, registry_enabled

    def clear_pending(new_state: GraphState) -> None:
        clear_pending_after_success(kb_name, cfg, new_state.build_id)

    if registry_enabled(cfg):
        staging = materialize_registry_build_source(kb_name, cfg)
        try:
            docs_dir = staging.__enter__()
        except Exception as exc:
            task = RebuildTask(
                task_id=str(uuid.uuid4()),
                status="failed",
                kb_name=kb_name,
                started_at=_now(),
                finished_at=_now(),
                error={"type": type(exc).__name__, "message": str(exc)},
                requested_mode=mode,
                effective_mode="full" if mode == "full" else mode,
            )
            app_state.rebuild_tasks[task.task_id] = task
            from .manual_library import build_rebuild_operations_summary

            def failed_operations_summary() -> dict[str, Any]:
                return build_rebuild_operations_summary(
                    kb_name=kb_name,
                    cfg=cfg,
                    task=task,
                    graph_state=app_state.kbs.get(kb_name),
                )

            task.operations_summary = failed_operations_summary  # type: ignore[attr-defined]
            return task
        try:
            task = app_state.start_rebuild(
                docs_dir,
                kb_name,
                cfg,
                embedder=embedder,
                on_success=clear_pending,
                mode=mode,
                allow_fallback=allow_fallback,
                is_library_rebuild=True,
                cleanup=lambda: staging.__exit__(None, None, None),
            )
        except Exception:
            staging.__exit__(None, None, None)
            raise
    else:
        docs_dir = library_root(kb_name, cfg)
        task = app_state.start_rebuild(
            docs_dir,
            kb_name,
            cfg,
            embedder=embedder,
            on_success=clear_pending,
            mode=mode,
            allow_fallback=allow_fallback,
            is_library_rebuild=True,
        )
    from .manual_library import build_rebuild_operations_summary

    def operations_summary() -> dict[str, Any]:
        return build_rebuild_operations_summary(
            kb_name=kb_name,
            cfg=cfg,
            task=task,
            graph_state=app_state.kbs.get(kb_name),
        )

    task.operations_summary = operations_summary  # type: ignore[attr-defined]
    return task
