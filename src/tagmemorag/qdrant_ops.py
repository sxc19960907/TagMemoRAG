from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .config import Settings
from .rebuild_impact import impact_path
from .storage.json_graph import JsonGraphStore
from .storage.qdrant_vector import QdrantVectorStore, SAFE_QDRANT_PAYLOAD_KEYS, collection_name

MISSING_VECTOR_SAMPLE_LIMIT = 10


def inspect_qdrant(
    kb_name: str,
    cfg: Settings,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    provider = cfg.vector_store.provider
    report: dict[str, Any] = {
        "kb_name": kb_name,
        "provider": provider,
        "configured": provider == "qdrant",
        "collection_name": collection_name(cfg.vector_store.collection_prefix, kb_name),
        "qdrant_url": cfg.vector_store.qdrant_url,
        "collection_exists": False,
        "graph_loaded": False,
        "graph_node_count": 0,
        "qdrant_point_count": 0,
        "missing_vector_count": 0,
        "missing_vector_sample": [],
        "sample_payload_keys": [],
        "payload_key_coverage": {key: 0 for key in sorted(SAFE_QDRANT_PAYLOAD_KEYS)},
        "last_qdrant_sync": _last_qdrant_sync(kb_name, cfg),
        "recommendations": [],
    }
    graph_node_ids = _graph_node_ids(kb_name, cfg)
    if graph_node_ids is not None:
        report["graph_loaded"] = True
        report["graph_node_count"] = len(graph_node_ids)
    else:
        report["recommendations"].append("build_or_load_kb_before_inspection")

    if provider != "qdrant":
        report["recommendations"].append("set_vector_store_provider_to_qdrant")
        return report

    store = QdrantVectorStore(
        kb_name=kb_name,
        dim=_configured_dim(kb_name, cfg),
        url=cfg.vector_store.qdrant_url,
        collection_prefix=cfg.vector_store.collection_prefix,
        timeout_seconds=cfg.vector_store.timeout_seconds,
        client_factory=client_factory,
    )
    try:
        store.client.get_collection(collection_name=store.collection_name)
        report["collection_exists"] = True
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__}
        report["recommendations"].append("ensure_qdrant_collection_exists_or_rebuild")
        return report

    records = _scroll_records(store)
    point_ids = {int(record.id) for record in records}
    report["qdrant_point_count"] = len(point_ids)

    payload_keys: set[str] = set()
    coverage = {key: 0 for key in sorted(SAFE_QDRANT_PAYLOAD_KEYS)}
    for record in records:
        payload = getattr(record, "payload", None) or {}
        safe_keys = sorted(key for key in payload if key in SAFE_QDRANT_PAYLOAD_KEYS)
        payload_keys.update(safe_keys)
        for key in safe_keys:
            coverage[key] += 1
    report["sample_payload_keys"] = sorted(payload_keys)
    report["payload_key_coverage"] = coverage

    if graph_node_ids is not None:
        missing = sorted(node_id for node_id in graph_node_ids if node_id not in point_ids)
        report["missing_vector_count"] = len(missing)
        report["missing_vector_sample"] = missing[:MISSING_VECTOR_SAMPLE_LIMIT]
        if missing:
            report["recommendations"].append("retry_incremental_rebuild_or_force_full_rebuild")
    if records and any(coverage[key] == 0 for key in ("build_id", "chunk_identity_key", "text_hash")):
        report["recommendations"].append("legacy_or_incomplete_payloads_detected_rebuild_refreshes_payloads")
    return report


def _graph_node_ids(kb_name: str, cfg: Settings) -> list[int] | None:
    graph_path = Path(cfg.storage.data_dir) / kb_name / "graph.json"
    meta_path = Path(cfg.storage.data_dir) / kb_name / "meta.json"
    if not graph_path.exists() or not meta_path.exists():
        return None
    graph = JsonGraphStore(graph_path).load()
    return sorted(int(node_id) for node_id in graph.nodes)


def _configured_dim(kb_name: str, cfg: Settings) -> int:
    meta_path = Path(cfg.storage.data_dir) / kb_name / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return int(meta.get("model_dim") or cfg.model.dim)
        except Exception:
            return int(cfg.model.dim)
    return int(cfg.model.dim)


def _scroll_records(store: QdrantVectorStore) -> list[Any]:
    records: list[Any] = []
    offset = None
    while True:
        page, offset = store.client.scroll(
            collection_name=store.collection_name,
            offset=offset,
            limit=256,
            with_vectors=False,
            with_payload=True,
        )
        records.extend(page)
        if offset is None:
            break
    return records


def _last_qdrant_sync(kb_name: str, cfg: Settings) -> dict[str, Any] | None:
    meta_path = Path(cfg.storage.data_dir) / kb_name / "meta.json"
    meta_sync = _read_qdrant_sync(meta_path)
    if meta_sync is not None:
        return meta_sync
    return _read_qdrant_sync(impact_path(kb_name, cfg.storage.data_dir))


def _read_qdrant_sync(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    sync = data.get("qdrant_sync")
    if not isinstance(sync, dict):
        return None
    allowed = {"provider", "strategy", "points_upserted", "points_deleted", "points_reused", "fallback_reason"}
    return {key: sync[key] for key in sorted(allowed) if key in sync}
