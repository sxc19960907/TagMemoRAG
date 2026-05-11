from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
import threading
import uuid

import numpy as np

from .config import Settings
from .embedder import create_embedder
from .errors import KbNotLoadedError, RebuildFailedError, RebuildInProgressError, StorageSchemaMismatchError
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
    rebuild_tasks: dict[str, RebuildTask] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _rebuild_lock: threading.Lock = field(default_factory=threading.Lock)

    def get_current(self, kb_name: str = "default") -> GraphState:
        with self._lock:
            if self.current is None or self.current.kb_name != kb_name:
                raise KbNotLoadedError(kb_name)
            return self.current

    def swap(self, new_state: GraphState) -> None:
        with self._lock:
            self.current = new_state

    def start_rebuild(self, docs_dir: str | Path, kb_name: str, cfg: Settings, embedder=None) -> RebuildTask:
        if not self._rebuild_lock.acquire(blocking=False):
            running = next((task.task_id for task in self.rebuild_tasks.values() if task.status == "running"), None)
            raise RebuildInProgressError(running)
        task_id = str(uuid.uuid4())
        task = RebuildTask(task_id=task_id, status="running", kb_name=kb_name, started_at=_now())
        self.rebuild_tasks[task_id] = task
        thread = threading.Thread(target=self._rebuild_worker, args=(task, docs_dir, kb_name, cfg, embedder), daemon=True)
        thread.start()
        return task

    def _rebuild_worker(self, task: RebuildTask, docs_dir: str | Path, kb_name: str, cfg: Settings, embedder) -> None:
        try:
            new_state = build_kb(docs_dir, kb_name, cfg, embedder=embedder, old_state=self.current)
            save_kb(new_state, cfg)
            self.swap(new_state)
            task.status = "done"
            task.build_id = new_state.build_id
        except Exception as exc:
            task.status = "failed"
            task.error = {"type": type(exc).__name__, "message": str(exc)}
        finally:
            task.finished_at = _now()
            self._rebuild_lock.release()


def build_kb(docs_dir: str | Path, kb_name: str, cfg: Settings, embedder=None, old_state: GraphState | None = None) -> GraphState:
    docs_root = Path(docs_dir)
    if not docs_root.exists():
        raise RebuildFailedError({"reason": "docs_dir does not exist", "docs_dir": str(docs_root)})
    embedder = embedder or create_embedder(cfg.model.name, cfg.model.device, cfg.model.batch_size, cfg.model.dim)
    chunks = []
    for path in sorted([*docs_root.rglob("*.md"), *docs_root.rglob("*.txt")]):
        chunks.extend(parse_document(path, cfg.parser.max_chars, cfg.parser.min_chars, root_dir=docs_root))
    texts = [chunk.text for chunk in chunks]
    vectors = embedder.encode_batch(texts) if texts else np.zeros((0, cfg.model.dim), dtype=np.float32)
    graph = build_graph(chunks, vectors, cfg.graph)
    anchor_store = _anchor_store(kb_name, cfg)
    old_anchors = anchor_store.load()
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
    return GraphState(graph=graph, vectors=vectors, anchors=anchors, build_id=build_id, kb_name=kb_name, meta=meta, unresolved_anchors=unresolved)


def save_kb(state: GraphState, cfg: Settings) -> None:
    root = _kb_dir(state.kb_name, cfg)
    JsonGraphStore(root / "graph.json").save(state.graph)
    NpzVectorStore(root / "vectors.npz").add(np.arange(state.vectors.shape[0]), state.vectors)
    JsonAnchorStore(root / "anchors.json").save(list(state.anchors.values()))

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
    loaded = JsonAnchorStore(root / "anchors.json").load()
    anchors = {anchor.node_id: anchor for anchor in loaded if anchor.node_id is not None}
    return GraphState(graph=graph, vectors=vectors, anchors=anchors, kb_name=kb_name, meta=meta, build_id=str(meta.get("built_at", _now())))


def _kb_dir(kb_name: str, cfg: Settings) -> Path:
    return Path(cfg.storage.data_dir) / kb_name


def _anchor_store(kb_name: str, cfg: Settings) -> JsonAnchorStore:
    return JsonAnchorStore(_kb_dir(kb_name, cfg) / "anchors.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
