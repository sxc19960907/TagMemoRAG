"""Tests for RerankCache (T3 Slice 3)."""

from __future__ import annotations

import threading

import pytest

from tagmemorag.reranker.cache import RerankCache


def _key(suffix: str = "x") -> tuple:
    return ("rid", "v1", "instr_hash", "query_hash", f"chunks_{suffix}")


def test_cache_round_trip():
    c = RerankCache(max_entries=10)
    k = _key()
    assert c.get(k) is None
    c.put(k, [("c1", 0.9), ("c2", 0.5)])
    assert c.get(k) == [("c1", 0.9), ("c2", 0.5)]


def test_cache_returns_defensive_copy():
    """Mutating the returned list must not corrupt cache contents."""
    c = RerankCache(max_entries=10)
    k = _key()
    c.put(k, [("c1", 0.9)])
    out1 = c.get(k)
    out1.append(("MUTATED", 0.0))
    out2 = c.get(k)
    assert out2 == [("c1", 0.9)]


def test_cache_lru_eviction():
    c = RerankCache(max_entries=2)
    c.put(_key("a"), [("c", 0.1)])
    c.put(_key("b"), [("c", 0.2)])
    c.put(_key("c"), [("c", 0.3)])  # evicts oldest = key("a")
    assert c.get(_key("a")) is None
    assert c.get(_key("b")) is not None
    assert c.get(_key("c")) is not None
    assert c.size() == 2


def test_cache_get_promotes_to_most_recent():
    c = RerankCache(max_entries=2)
    c.put(_key("a"), [("c", 0.1)])
    c.put(_key("b"), [("c", 0.2)])
    # Access a; b becomes oldest
    _ = c.get(_key("a"))
    c.put(_key("c"), [("c", 0.3)])  # should evict b, keep a
    assert c.get(_key("a")) is not None
    assert c.get(_key("b")) is None
    assert c.get(_key("c")) is not None


def test_cache_overwrite_promotes():
    c = RerankCache(max_entries=2)
    c.put(_key("a"), [("c", 0.1)])
    c.put(_key("b"), [("c", 0.2)])
    c.put(_key("a"), [("c", 0.99)])  # overwrite
    c.put(_key("c"), [("c", 0.3)])  # evicts b
    assert c.get(_key("a")) == [("c", 0.99)]
    assert c.get(_key("b")) is None


def test_cache_clear():
    c = RerankCache(max_entries=10)
    c.put(_key("a"), [("c", 0.1)])
    c.put(_key("b"), [("c", 0.2)])
    c.clear()
    assert c.size() == 0
    assert c.get(_key("a")) is None


def test_cache_key_isolation():
    """Different keys produce different cache slots."""
    c = RerankCache(max_entries=10)
    c.put(("rid1", "v1", "ih", "qh", "ch"), [("c", 0.1)])
    c.put(("rid2", "v1", "ih", "qh", "ch"), [("c", 0.2)])
    c.put(("rid1", "v2", "ih", "qh", "ch"), [("c", 0.3)])
    c.put(("rid1", "v1", "DIFFERENT", "qh", "ch"), [("c", 0.4)])
    assert c.get(("rid1", "v1", "ih", "qh", "ch")) == [("c", 0.1)]
    assert c.get(("rid2", "v1", "ih", "qh", "ch")) == [("c", 0.2)]
    assert c.get(("rid1", "v2", "ih", "qh", "ch")) == [("c", 0.3)]
    assert c.get(("rid1", "v1", "DIFFERENT", "qh", "ch")) == [("c", 0.4)]


def test_cache_max_entries_validation():
    with pytest.raises(ValueError):
        RerankCache(max_entries=0)


def test_cache_thread_safety_smoke():
    """Many threads put + get — no race-induced corruption."""
    c = RerankCache(max_entries=200)

    def worker(prefix: str):
        for i in range(50):
            c.put((prefix, str(i)), [("c", float(i))])
            _ = c.get((prefix, str(i)))

    threads = [threading.Thread(target=worker, args=(f"p{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 8 threads × 50 entries = 400 puts; cap=200 → exactly 200 entries
    assert c.size() == 200
