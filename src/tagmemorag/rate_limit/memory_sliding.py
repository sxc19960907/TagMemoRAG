from __future__ import annotations

import threading
import time

from .base import RateLimitResult, RateLimitStore


class InMemorySlidingWindowStore(RateLimitStore):
    def __init__(self, window_seconds: int = 60, now_fn=time.time):
        self._window = int(window_seconds)
        self._now = now_fn
        self._state: dict[str, tuple[int, int, int]] = {}
        self._lock = threading.Lock()

    def check_and_incr(self, key_id: str, limit_per_minute: int, now: float | None = None) -> RateLimitResult:
        t = float(now if now is not None else self._now())
        if limit_per_minute <= 0:
            reset = int((t // self._window + 1) * self._window)
            return RateLimitResult(False, 0, limit_per_minute, reset, max(1, reset - int(t)))
        with self._lock:
            window_start = int(t // self._window * self._window)
            ws, curr, prev = self._state.get(key_id, (window_start, 0, 0))
            elapsed_windows = int((window_start - ws) // self._window)
            if elapsed_windows <= 0:
                pass
            elif elapsed_windows == 1:
                prev = curr
                curr = 0
                ws = window_start
            else:
                prev = 0
                curr = 0
                ws = window_start
            offset = (t - ws) / self._window
            approx_used = prev * (1 - offset) + curr
            reset = int(ws + self._window)
            if approx_used >= limit_per_minute:
                self._state[key_id] = (ws, curr, prev)
                return RateLimitResult(False, 0, limit_per_minute, reset, max(1, reset - int(t)))
            curr += 1
            self._state[key_id] = (ws, curr, prev)
            remaining = max(0, limit_per_minute - int(approx_used) - 1)
            return RateLimitResult(True, remaining, limit_per_minute, reset, 0)
