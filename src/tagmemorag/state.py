from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
import threading
import time
import uuid

import numpy as np
import structlog

from .config import Settings
from .embedder import create_embedder
from .errors import KbNotLoadedError, RebuildFailedError, RebuildInProgressError, ShuttingDownError, StorageSchemaMismatchError
from .graph_builder import build_graph
from .parser import parse_document
from .storage.atomic import atomic_write
from .storage.json_anchor import JsonAnchorStore
from .storage.json_graph import JsonGraphStore
from .storage.npz_vector import NpzVectorStore
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

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "kb_name": self.kb_name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "build_id": self.build_id,
        }


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

    def start_rebuild(self, docs_dir: str | Path, kb_name: str, cfg: Settings, embedder=None) -> RebuildTask:
        with self._lock:
            if self.is_shutting_down:
                raise ShuttingDownError()
        rebuild_lock = self.lock_for(kb_name)
        if not rebuild_lock.acquire(blocking=False):
            running = next(
                (task.task_id for task in self.rebuild_tasks.values() if task.status == "running" and task.kb_name == kb_name),
                None,
            )
            raise RebuildInProgressError(running)
        task_id = str(uuid.uuid4())
        task = RebuildTask(task_id=task_id, status="running", kb_name=kb_name, started_at=_now())
        self.rebuild_tasks[task_id] = task
        structlog.get_logger().info("rebuild_started", task_id=task_id, docs_dir=str(docs_dir), kb_name=kb_name)
        thread = threading.Thread(target=self._rebuild_worker, args=(task, docs_dir, kb_name, cfg, embedder, rebuild_lock), daemon=True)
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
    ) -> None:
        t0 = time.perf_counter()
        try:
            old_state = self.kbs.get(kb_name)
            new_state = build_kb(docs_dir, kb_name, cfg, embedder=embedder, old_state=old_state)
            save_kb(new_state, cfg)
            self.swap_kb(kb_name, new_state)
            task.status = "done"
            task.build_id = new_state.build_id
            structlog.get_logger().info(
                "rebuild_done",
                task_id=task.task_id,
                kb_name=kb_name,
                build_id=new_state.build_id,
                duration_ms=round((time.perf_counter() - t0) * 1000.0, 3),
                chunk_count=new_state.graph.number_of_nodes(),
            )
        except Exception as exc:
            task.status = "failed"
            task.error = {"type": type(exc).__name__, "message": str(exc)}
            structlog.get_logger().error(
                "rebuild_failed",
                task_id=task.task_id,
                kb_name=kb_name,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        finally:
            task.finished_at = _now()
            rebuild_lock.release()


def build_kb(docs_dir: str | Path, kb_name: str, cfg: Settings, embedder=None, old_state: GraphState | None = None) -> GraphState:
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
    for path in sorted([*docs_root.rglob("*.md"), *docs_root.rglob("*.txt")]):
        chunks.extend(parse_document(path, cfg.parser.max_chars, cfg.parser.min_chars, root_dir=docs_root))
    texts = [chunk.text for chunk in chunks]
    vectors = embedder.encode_batch(texts) if texts else np.zeros((0, cfg.model.dim), dtype=np.float32)
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


def save_kb(state: GraphState, cfg: Settings) -> None:
    root = _kb_dir(state.kb_name, cfg)
    JsonGraphStore(root / "graph.json").save(state.graph)
    NpzVectorStore(root / "vectors.npz").add(np.arange(state.vectors.shape[0]), state.vectors)
    JsonAnchorStore(root / "anchors.json").save(list(state.anchors.values()), version=state.anchors_version)

    def write_meta(tmp_path: Path) -> None:
        tmp_path.write_text(json.dumps(state.meta, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

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
    _, vectors = NpzVectorStore(root / "vectors.npz").load()
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
