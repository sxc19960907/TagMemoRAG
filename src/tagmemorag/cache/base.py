from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class QueryCache(ABC):
    @abstractmethod
    def get(self, cache_key: str) -> dict[str, Any] | None:
        """Return a cached payload."""

    @abstractmethod
    def set(self, cache_key: str, value: dict[str, Any], kb_name: str = "") -> None:
        """Store a cached payload."""

    @abstractmethod
    def clear(self, kb_name: str | None = None) -> int:
        """Clear all entries or entries for one KB; return count removed."""
