"""LRU rerank cache (Architecture v2 § A3 / Decision D3).

Single-process in-memory cache. Key intentionally generation-independent —
same chunk_id + query produce the same rerank score regardless of which
IndexGeneration served it (reranker doesn't depend on vector features).

Cache value is the adapter-level outcome (chunk_id → raw_score pairs);
calibration happens after fetch, since the calibrator may change without
invalidating the cache.
"""

from __future__ import annotations

import collections
import threading
from typing import Iterable


class RerankCache:
    """OrderedDict-backed LRU; thread-safe via a single Lock."""

    def __init__(self, max_entries: int = 5000):
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._cap = int(max_entries)
        self._data: "collections.OrderedDict[tuple, list[tuple[str, float]]]" = (
            collections.OrderedDict()
        )
        self._lock = threading.Lock()

    def get(self, key: tuple) -> list[tuple[str, float]] | None:
        with self._lock:
            value = self._data.get(key)
            if value is None:
                return None
            # Move to end (most recently used)
            self._data.move_to_end(key)
            return list(value)  # defensive copy

    def put(self, key: tuple, value: Iterable[tuple[str, float]]) -> None:
        items = list(value)
        with self._lock:
            self._data[key] = items
            self._data.move_to_end(key)
            while len(self._data) > self._cap:
                self._data.popitem(last=False)  # evict oldest

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._data)


__all__ = ["RerankCache"]
