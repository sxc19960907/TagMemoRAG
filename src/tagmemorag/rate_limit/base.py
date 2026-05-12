from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    limit: int
    reset_epoch: int
    retry_after_seconds: int = 0


class RateLimitStore(ABC):
    @abstractmethod
    def check_and_incr(self, key_id: str, limit_per_minute: int, now: float | None = None) -> RateLimitResult:
        """Check and count a request for one key."""
