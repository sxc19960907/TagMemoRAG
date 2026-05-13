from __future__ import annotations

from tagmemorag.api import SearchRequest, _compute_cache_key, _compute_search_id
from tagmemorag.cache.lru_ttl import LRUTTLCache
from tagmemorag.types import GraphState

import networkx as nx
import numpy as np


def test_lru_ttl_cache_round_trip_ttl_and_clear():
    now = [1000.0]
    cache = LRUTTLCache(max_entries=2, ttl_seconds=10, now_fn=lambda: now[0])

    cache.set("a", {"value": 1}, kb_name="kb-a")
    assert cache.get("a") == {"value": 1}
    now[0] += 11
    assert cache.get("a") is None

    cache.set("a", {"value": 1}, kb_name="kb-a")
    cache.set("b", {"value": 2}, kb_name="kb-b")
    assert cache.clear("kb-a") == 1
    assert cache.get("a") is None
    assert cache.get("b") == {"value": 2}
    assert cache.clear() == 1


def test_lru_ttl_cache_evicts_oldest():
    cache = LRUTTLCache(max_entries=2, ttl_seconds=10, now_fn=lambda: 1000.0)

    cache.set("a", {"value": 1})
    cache.set("b", {"value": 2})
    assert cache.get("a") == {"value": 1}
    cache.set("c", {"value": 3})

    assert cache.get("b") is None
    assert cache.get("a") == {"value": 1}
    assert cache.get("c") == {"value": 3}


def test_cache_key_is_sensitive_to_kb_build_anchors_and_params():
    graph = nx.Graph()
    state = GraphState(graph=graph, vectors=np.zeros((0, 64)), build_id="build-a", kb_name="kb-a", anchors_version=1)
    req = SearchRequest(question="  a   b  ", kb_name="kb-a", top_k=3)
    base = _compute_cache_key(req, state)

    assert base == _compute_cache_key(SearchRequest(question="a b", kb_name="kb-a", top_k=3), state)
    assert base != _compute_cache_key(SearchRequest(question="a b", kb_name="kb-b", top_k=3), state)
    assert base != _compute_cache_key(SearchRequest(question="a b", kb_name="kb-a", top_k=4), state)
    assert base != _compute_cache_key(req, GraphState(graph=graph, vectors=np.zeros((0, 64)), build_id="build-b", kb_name="kb-a"))
    assert base != _compute_cache_key(
        req,
        GraphState(graph=graph, vectors=np.zeros((0, 64)), build_id="build-a", kb_name="kb-a", anchors_version=2),
    )
    assert base != _compute_cache_key(SearchRequest(question="a b", kb_name="kb-a", top_k=3, debug=True), state)


def test_cache_key_includes_canonical_filters():
    graph = nx.Graph()
    state = GraphState(graph=graph, vectors=np.zeros((0, 64)), build_id="build-a", kb_name="kb-a", anchors_version=1)
    base = _compute_cache_key(SearchRequest(question="a", kb_name="kb-a"), state)
    filtered = _compute_cache_key(
        SearchRequest(
            question="a",
            kb_name="kb-a",
            filters={"product_category": "Fridge", "tags": ["Temperature Setting", "Maintenance"]},
        ),
        state,
    )
    same_filtered = _compute_cache_key(
        SearchRequest(
            question="a",
            kb_name="kb-a",
            filters={"product_category": "fridge", "tags": ["maintenance", "temperature-setting"]},
        ),
        state,
    )

    assert base != filtered
    assert filtered == same_filtered


def test_search_id_changes_with_trace_but_uses_same_request_canonicalization():
    graph = nx.Graph()
    state = GraphState(graph=graph, vectors=np.zeros((0, 64)), build_id="build-a", kb_name="kb-a", anchors_version=1)
    request = SearchRequest(question="  a   b  ", kb_name="kb-a", top_k=3)

    first = _compute_search_id(request, state, "trace-a")

    assert first == _compute_search_id(SearchRequest(question="a b", kb_name="kb-a", top_k=3), state, "trace-a")
    assert first != _compute_search_id(request, state, "trace-b")
    assert first != _compute_search_id(SearchRequest(question="a b", kb_name="kb-a", top_k=3, debug=True), state, "trace-a")
