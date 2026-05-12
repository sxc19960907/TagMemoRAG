from __future__ import annotations

from collections import OrderedDict
from typing import Any
import threading
import time

from .base import QueryCache


class LRUTTLCache(QueryCache):
    def __init__(self, max_entries: int = 10000, ttl_seconds: int = 3600, now_fn=time.time):
        self._max_entries = int(max_entries)
        self._ttl_seconds = int(ttl_seconds)
        self._now = now_fn
        self._data: OrderedDict[str, tuple[dict[str, Any], float, str]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, cache_key: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._data.get(cache_key)
            if entry is None:
                return None
            value, expiry, _kb_name = entry
            if self._now() >= expiry:
                self._data.pop(cache_key, None)
                return None
            self._data.move_to_end(cache_key)
            return dict(value)

    def set(self, cache_key: str, value: dict[str, Any], kb_name: str = "") -> None:
        if self._max_entries <= 0 or self._ttl_seconds <= 0:
            return
        with self._lock:
            if cache_key in self._data:
                self._data.move_to_end(cache_key)
            self._data[cache_key] = (dict(value), self._now() + self._ttl_seconds, kb_name)
            while len(self._data) > self._max_entries:
                self._data.popitem(last=False)

    def clear(self, kb_name: str | None = None) -> int:
        with self._lock:
            if kb_name is None:
                count = len(self._data)
                self._data.clear()
                return count
            keys = [key for key, (_value, _expiry, item_kb) in self._data.items() if item_kb == kb_name]
            for key in keys:
                self._data.pop(key, None)
            return len(keys)
