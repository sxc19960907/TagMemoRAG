from __future__ import annotations

import re
from typing import Any, Callable

import numpy as np

from tagmemorag.errors import ErrorCode, InvalidConfigError, ServiceError
from tagmemorag.storage.base import VectorStore


SAFE_QDRANT_PAYLOAD_KEYS = {
    "kb_name",
    "node_id",
    "build_id",
    "chunk_id",
    "chunk_identity_key",
    "doc_id",
    "manual_id",
    "source_file",
    "text_hash",
}


class QdrantVectorStore(VectorStore):
    def __init__(
        self,
        *,
        kb_name: str,
        dim: int,
        url: str,
        collection_prefix: str = "tagmemorag",
        timeout_seconds: float = 10.0,
        client: Any | None = None,
        client_factory: Callable[..., Any] | None = None,
    ):
        self.kb_name = kb_name
        self.dim = int(dim)
        self.url = url
        self.collection_name = collection_name(collection_prefix, kb_name)
        self.client = client or type(self)._create_client(client_factory, url=url, timeout=timeout_seconds)

    def add(self, ids: np.ndarray, vecs: np.ndarray, payloads: list[dict[str, Any]] | None = None) -> None:
        self.update(ids, vecs, payloads=payloads)

    def update(self, ids: np.ndarray, vecs: np.ndarray, payloads: list[dict[str, Any]] | None = None) -> None:
        ids = np.asarray(ids, dtype=np.int64)
        vecs = np.asarray(vecs, dtype=np.float32)
        if vecs.ndim != 2 or vecs.shape[1] != self.dim:
            raise ServiceError(
                ErrorCode.STORAGE_SCHEMA_MISMATCH,
                "Qdrant vector dimension does not match configured model dimension.",
                {"expected": self.dim, "actual": int(vecs.shape[1]) if vecs.ndim == 2 else None},
            )
        if len(ids) != len(vecs):
            raise ServiceError(
                ErrorCode.STORAGE_SCHEMA_MISMATCH,
                "Qdrant vector ids and vectors have different lengths.",
                {"ids": len(ids), "vectors": len(vecs)},
            )
        if payloads is not None and len(payloads) != len(ids):
            raise ServiceError(
                ErrorCode.STORAGE_SCHEMA_MISMATCH,
                "Qdrant payload count does not match vector ids.",
                {"ids": len(ids), "payloads": len(payloads)},
            )
        try:
            self._ensure_collection()
            points = [
                self._point_struct(int(node_id), vecs[index], payloads[index] if payloads is not None else None)
                for index, node_id in enumerate(ids)
            ]
            if points:
                self.client.upsert(collection_name=self.collection_name, points=points)
        except ServiceError:
            raise
        except Exception as exc:
            raise _storage_error("Failed to write vectors to Qdrant.", exc, self.collection_name) from exc

    def delete(self, ids: np.ndarray | list[int]) -> None:
        ids_array = np.asarray(ids, dtype=np.int64)
        if len(ids_array) == 0:
            return
        try:
            self.client.delete(collection_name=self.collection_name, points_selector=[int(node_id) for node_id in ids_array])
        except Exception as exc:
            raise _storage_error("Failed to delete vectors from Qdrant.", exc, self.collection_name) from exc

    def update_payloads(self, ids: np.ndarray | list[int], payloads: list[dict[str, Any]]) -> None:
        ids_array = np.asarray(ids, dtype=np.int64)
        if len(ids_array) == 0:
            return
        if len(payloads) != len(ids_array):
            raise ServiceError(
                ErrorCode.STORAGE_SCHEMA_MISMATCH,
                "Qdrant payload count does not match vector ids.",
                {"ids": len(ids_array), "payloads": len(payloads)},
            )
        try:
            safe_payloads = [_safe_payload(payload) for payload in payloads]
            try:
                self._update_payloads_batch(ids_array, safe_payloads)
            except NotImplementedError:
                self._update_payloads_per_point(ids_array, safe_payloads)
        except Exception as exc:
            raise _storage_error("Failed to update Qdrant payloads.", exc, self.collection_name) from exc

    def _update_payloads_batch(self, ids: np.ndarray, payloads: list[dict[str, Any]]) -> None:
        batch_update = getattr(self.client, "batch_update_points", None)
        if not callable(batch_update):
            raise NotImplementedError
        if not self._uses_real_client():
            operations = [{"set_payload": {"payload": payload, "points": [int(ids[index])]}} for index, payload in enumerate(payloads)]
        else:
            try:
                from qdrant_client.models import SetPayload, SetPayloadOperation
            except ImportError as exc:
                raise _missing_dependency() from exc
            operations = [
                SetPayloadOperation(set_payload=SetPayload(payload=payload, points=[int(ids[index])]))
                for index, payload in enumerate(payloads)
            ]
        batch_update(collection_name=self.collection_name, update_operations=operations)

    def _update_payloads_per_point(self, ids: np.ndarray, payloads: list[dict[str, Any]]) -> None:
        for index, node_id in enumerate(ids):
            self.client.set_payload(
                collection_name=self.collection_name,
                points=[int(node_id)],
                payload=payloads[index],
            )

    def load(self, ids: np.ndarray | list[int] | None = None) -> tuple[np.ndarray, np.ndarray]:
        try:
            if ids is None:
                ids_array = self._scroll_ids()
            else:
                ids_array = np.asarray(ids, dtype=np.int64)
            if len(ids_array) == 0:
                return ids_array, np.zeros((0, self.dim), dtype=np.float32)
            records = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[int(node_id) for node_id in ids_array],
                with_vectors=True,
                with_payload=False,
            )
        except Exception as exc:
            raise _storage_error("Failed to load vectors from Qdrant.", exc, self.collection_name) from exc

        by_id = {int(record.id): _record_vector(record) for record in records}
        missing = [int(node_id) for node_id in ids_array if int(node_id) not in by_id]
        if missing:
            raise ServiceError(
                ErrorCode.STORAGE_LOAD_FAILED,
                "Qdrant collection is missing vectors for graph nodes.",
                {"collection": self.collection_name, "missing_node_ids": missing[:10], "missing_count": len(missing)},
            )
        vecs = np.asarray([by_id[int(node_id)] for node_id in ids_array], dtype=np.float32)
        if vecs.ndim != 2 or vecs.shape[1] != self.dim:
            raise ServiceError(
                ErrorCode.STORAGE_LOAD_FAILED,
                "Loaded Qdrant vectors do not match configured model dimension.",
                {"collection": self.collection_name, "expected": self.dim, "actual": int(vecs.shape[1]) if vecs.ndim == 2 else None},
            )
        return ids_array, vecs

    def search(self, query_vec: np.ndarray, k: int) -> list[tuple[int, float]]:
        ids, vecs = self.load()
        if len(ids) == 0:
            return []
        sims = vecs @ np.asarray(query_vec, dtype=np.float32)
        count = min(k, len(sims))
        top = np.argpartition(-sims, count - 1)[:count]
        return sorted(((int(ids[i]), float(sims[i])) for i in top), key=lambda item: (-item[1], item[0]))

    def search_candidates(self, query_vec: np.ndarray, k: int) -> list[tuple[int, float]]:
        if k <= 0:
            return []
        vector = np.asarray(query_vec, dtype=np.float32)
        try:
            if self._uses_real_client():
                records = self._search_real_client(vector, int(k))
            else:
                records = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=vector.astype(float).tolist(),
                    limit=int(k),
                    with_payload=False,
                    with_vectors=False,
                )
        except Exception as exc:
            raise _storage_error("Failed to query ANN candidates from Qdrant.", exc, self.collection_name) from exc
        candidates: list[tuple[int, float]] = []
        for record in records:
            candidates.append((int(record.id), float(getattr(record, "score", 0.0))))
        return sorted(candidates, key=lambda item: (-item[1], item[0]))

    def _search_real_client(self, vector: np.ndarray, k: int):
        query_vector = vector.astype(float).tolist()
        search = getattr(self.client, "search", None)
        if callable(search):
            return search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=k,
                with_payload=False,
                with_vectors=False,
            )
        query_points = getattr(self.client, "query_points", None)
        if callable(query_points):
            response = query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=k,
                with_payload=False,
                with_vectors=False,
            )
            return list(getattr(response, "points", response))
        raise NotImplementedError("Qdrant client does not support vector search.")

    def get(self, node_id: int) -> np.ndarray:
        _, vecs = self.load([node_id])
        return vecs[0]

    def _ensure_collection(self) -> None:
        try:
            self.client.get_collection(collection_name=self.collection_name)
            return
        except Exception:
            pass
        try:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=self._vector_params(self.dim),
            )
        except Exception as exc:
            raise _storage_error("Failed to create Qdrant collection.", exc, self.collection_name) from exc

    def _scroll_ids(self) -> np.ndarray:
        ids: list[int] = []
        offset = None
        while True:
            records, offset = self.client.scroll(
                collection_name=self.collection_name,
                offset=offset,
                limit=256,
                with_vectors=False,
                with_payload=False,
            )
            ids.extend(int(record.id) for record in records)
            if offset is None:
                break
        return np.asarray(sorted(ids), dtype=np.int64)

    def _point_struct(self, node_id: int, vector: np.ndarray, payload: dict[str, Any] | None = None):
        point_payload = {"kb_name": self.kb_name, "node_id": node_id}
        if payload:
            point_payload.update(_safe_payload(payload))
        if not self._uses_real_client():
            return _SimplePoint(id=node_id, vector=vector.astype(float).tolist(), payload=point_payload)
        try:
            from qdrant_client.models import PointStruct
        except ImportError as exc:
            raise _missing_dependency() from exc
        return PointStruct(
            id=node_id,
            vector=vector.astype(float).tolist(),
            payload=point_payload,
        )

    def _vector_params(self, dim: int):
        if not self._uses_real_client():
            return {"size": dim, "distance": "Cosine"}
        try:
            from qdrant_client.models import Distance, VectorParams
        except ImportError as exc:
            raise _missing_dependency() from exc
        return VectorParams(size=dim, distance=Distance.COSINE)

    def _uses_real_client(self) -> bool:
        return self.client.__class__.__module__.startswith("qdrant_client")

    @staticmethod
    def _create_client(client_factory: Callable[..., Any] | None, **kwargs):
        if client_factory is not None:
            return client_factory(**kwargs)
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise _missing_dependency() from exc
        return QdrantClient(**kwargs)


def collection_name(prefix: str, kb_name: str) -> str:
    safe_prefix = _safe_collection_part(prefix or "tagmemorag")
    safe_kb = _safe_collection_part(kb_name or "default")
    return f"{safe_prefix}_{safe_kb}"


def _safe_collection_part(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip())
    normalized = re.sub(r"-+", "-", normalized).strip("-_")
    return normalized or "default"


class _SimplePoint:
    def __init__(self, *, id: int, vector: list[float], payload: dict[str, Any]):
        self.id = id
        self.vector = vector
        self.payload = payload


def _record_vector(record: Any) -> list[float]:
    vector = getattr(record, "vector", None)
    if isinstance(vector, dict):
        vector = next(iter(vector.values()), None)
    if vector is None:
        raise ServiceError(ErrorCode.STORAGE_LOAD_FAILED, "Qdrant point did not include a vector.")
    return list(vector)


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in SAFE_QDRANT_PAYLOAD_KEYS or value is None:
            continue
        if key == "node_id":
            safe[key] = int(value)
        else:
            safe[key] = str(value)
    return safe


def _missing_dependency() -> InvalidConfigError:
    return InvalidConfigError(
        "qdrant-client is required when vector_store.provider=qdrant.",
        {"dependency": "qdrant-client"},
    )


def _storage_error(message: str, exc: Exception, collection: str) -> ServiceError:
    return ServiceError(
        ErrorCode.STORAGE_LOAD_FAILED,
        message,
        {"collection": collection, "error_type": type(exc).__name__, "message": str(exc)},
    )
