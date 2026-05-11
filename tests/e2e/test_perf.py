from __future__ import annotations

import time

import numpy as np

from tagmemorag.config import GraphConfig
from tagmemorag.graph_builder import build_graph
from tagmemorag.types import Chunk
from tagmemorag.wave_searcher import wave_search


def test_1000_node_graph_build_and_search_budget():
    chunks = [
        Chunk(f"节点 {i} 蒸汽 清洗 E05", f"节点 {i}", (f"节点 {i}",), 1, i + 1, "perf.md")
        for i in range(1000)
    ]
    rng = np.random.default_rng(42)
    vectors = rng.normal(size=(1000, 64)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)

    start = time.perf_counter()
    graph = build_graph(chunks, vectors, GraphConfig(sim_threshold=2.0))
    build_seconds = time.perf_counter() - start
    assert build_seconds < 3.0

    query = vectors[0]
    start = time.perf_counter()
    for _ in range(100):
        results = wave_search(query, graph, vectors, {}, top_k=5)
    avg_ms = (time.perf_counter() - start) * 1000 / 100
    assert results
    assert avg_ms < 20.0
