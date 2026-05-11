from __future__ import annotations

import numpy as np

from tagmemorag.config import GraphConfig
from tagmemorag.graph_builder import build_graph
from tagmemorag.types import Anchor, Chunk
from tagmemorag.wave_searcher import wave_search


def test_build_graph_semantic_and_structure_edges():
    chunks = [
        Chunk("蒸汽功能说明", "蒸汽", ("操作", "蒸汽"), 2, 1, "x.md"),
        Chunk("蒸汽喷嘴清洗", "清洗", ("维护", "清洗"), 2, 2, "x.md"),
        Chunk("电源连接", "电源", ("安装", "电源"), 2, 3, "x.md"),
    ]
    vectors = np.array([[1, 0], [0.9, 0.1], [0, 1]], dtype=np.float32)
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    graph = build_graph(chunks, vectors, GraphConfig(sim_threshold=0.8))
    assert graph.has_edge(0, 1)
    assert graph.has_edge(1, 2)
    assert graph[0][1]["weight"] <= 1.0


def test_wave_search_anchor_and_aggregate_modes():
    chunks = [
        Chunk("安全停机", "安全", ("安全",), 1, 1, "x.md"),
        Chunk("紧急断电", "断电", ("安全", "断电"), 2, 2, "x.md"),
        Chunk("普通说明", "普通", ("普通",), 1, 3, "x.md"),
    ]
    vectors = np.array([[1, 0], [0.7, 0.7], [0, 1]], dtype=np.float32)
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    graph = build_graph(chunks, vectors, GraphConfig(sim_threshold=0.1))
    query = np.array([1, 0], dtype=np.float32)
    anchors = {0: Anchor(anchor_key=graph.nodes[0]["anchor_key"], label="紧急", boost=2.0, propagation_boost=2.0, node_id=0)}
    boosted_source = wave_search(query, graph, vectors, anchors, top_k=3, source_k=1, steps=0, aggregate="max")
    default_prop = wave_search(
        query,
        graph,
        vectors,
        {0: Anchor(anchor_key=graph.nodes[0]["anchor_key"], label="紧急", boost=2.0, propagation_boost=1.0, node_id=0)},
        top_k=3,
        source_k=1,
        steps=1,
        aggregate="max",
    )
    max_results = wave_search(query, graph, vectors, anchors, top_k=3, source_k=1, steps=1, aggregate="max")
    sum_results = wave_search(query, graph, vectors, anchors, top_k=3, source_k=1, steps=2, aggregate="sum")
    assert boosted_source[0].node_id == 0
    assert boosted_source[0].score == 2.0
    assert sum_results[0].score >= max_results[0].score
    default_neighbor = next(result.score for result in default_prop if result.node_id == 1)
    boosted_neighbor = next(result.score for result in max_results if result.node_id == 1)
    assert boosted_neighbor > default_neighbor
