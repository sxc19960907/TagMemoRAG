from __future__ import annotations

import threading

from tagmemorag.rate_limit.memory_sliding import InMemorySlidingWindowStore


def test_sliding_window_limit_and_reset():
    now = [1000.0]
    store = InMemorySlidingWindowStore(window_seconds=60, now_fn=lambda: now[0])

    assert [store.check_and_incr("key", 3).allowed for _ in range(3)] == [True, True, True]
    denied = store.check_and_incr("key", 3)
    assert denied.allowed is False
    assert denied.retry_after_seconds > 0

    now[0] += 121
    assert store.check_and_incr("key", 3).allowed is True


def test_rate_limit_keys_are_independent():
    store = InMemorySlidingWindowStore(window_seconds=60, now_fn=lambda: 1000.0)

    assert store.check_and_incr("a", 1).allowed is True
    assert store.check_and_incr("a", 1).allowed is False
    assert store.check_and_incr("b", 1).allowed is True


def test_rate_limit_is_thread_safe():
    store = InMemorySlidingWindowStore(window_seconds=60, now_fn=lambda: 1000.0)
    allowed = []
    lock = threading.Lock()

    def hit():
        for _ in range(10):
            result = store.check_and_incr("key", 11)
            with lock:
                allowed.append(result.allowed)

    threads = [threading.Thread(target=hit) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(allowed) == 11


def test_zero_limit_denies():
    store = InMemorySlidingWindowStore(window_seconds=60, now_fn=lambda: 1000.0)

    assert store.check_and_incr("key", 0).allowed is False
