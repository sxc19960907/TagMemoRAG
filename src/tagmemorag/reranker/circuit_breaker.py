"""Process-internal circuit breaker for reranker vendor calls (D4).

Simplified breaker without independent half-open state:
- Failures counted; threshold breach → open.
- Cooldown elapses → next call retries vendor.
- Success resets failure counter.

Multi-process deployments each have independent breakers. Acceptable for T3
because vendor health diverges per network path; cross-process consensus
not needed.
"""

from __future__ import annotations

import threading
import time


class CircuitBreaker:
    def __init__(self, threshold: int = 3, cooldown_s: float = 30.0):
        if threshold < 1:
            raise ValueError("threshold must be >= 1")
        if cooldown_s < 0:
            raise ValueError("cooldown_s must be >= 0")
        self._threshold = int(threshold)
        self._cooldown_s = float(cooldown_s)
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        """Returns True if the breaker is currently rejecting calls.

        Side effect: when cooldown has elapsed, resets state and returns False
        (next call retries vendor).
        """
        with self._lock:
            if self._opened_at is None:
                return False
            if time.monotonic() - self._opened_at < self._cooldown_s:
                return True
            # Cooldown elapsed; reset
            self._opened_at = None
            self._failures = 0
            return False

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._threshold:
                self._opened_at = time.monotonic()

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def state(self) -> dict:
        """Snapshot for tests / admin (T5+) endpoints."""
        with self._lock:
            return {
                "failures": self._failures,
                "opened_at": self._opened_at,
                "is_open": self._opened_at is not None
                and (time.monotonic() - self._opened_at) < self._cooldown_s,
                "threshold": self._threshold,
                "cooldown_s": self._cooldown_s,
            }


__all__ = ["CircuitBreaker"]
