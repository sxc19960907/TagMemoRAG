from __future__ import annotations

import numpy as np

from tagmemorag.config import GraphConfig
from tagmemorag.graph_builder import build_graph
from tagmemorag.types import Anchor, Chunk
from tagmemorag.wave_searcher import filter_node_ids, wave_search


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


def test_result_includes_manual_metadata_fields():
    chunks = [
        Chunk(
            "冷藏室温度设置",
            "温度",
            ("温度",),
            1,
            1,
            "fridge.md",
            metadata={
                "manual_id": "fridge-manual",
                "title": "Fridge Manual",
                "brand": "Gorenje",
                "product_category": "fridge",
                "product_model": "NRK6192",
                "language": "zh-CN",
                "version": "v1",
                "tags": ["temperature-setting"],
            },
        )
    ]
    vectors = np.array([[1, 0]], dtype=np.float32)
    graph = build_graph(chunks, vectors)

    result = wave_search(np.array([1, 0], dtype=np.float32), graph, vectors, top_k=1, source_k=1, steps=0)[0]
    payload = result.to_dict()

    assert payload["manual_id"] == "fridge-manual"
    assert payload["manual_title"] == "Fridge Manual"
    assert payload["brand"] == "Gorenje"
    assert payload["tags"] == ["temperature-setting"]
    assert payload["metadata"]["product_model"] == "NRK6192"


def test_filter_node_ids_and_wave_search_stay_within_eligible_nodes():
    chunks = [
        Chunk(
            "冷藏室温度设置",
            "温度",
            ("温度",),
            1,
            1,
            "fridge.md",
            metadata={"manual_id": "fridge", "product_category": "fridge", "product_model": "NRK6192", "tags": ["temperature-setting"]},
        ),
        Chunk(
            "咖啡机蒸汽清洗",
            "清洗",
            ("清洗",),
            1,
            1,
            "coffee.md",
            metadata={"manual_id": "coffee", "product_category": "coffee", "product_model": "CM1", "tags": ["maintenance"]},
        ),
    ]
    vectors = np.array([[1, 0], [0.95, 0.05]], dtype=np.float32)
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    graph = build_graph(chunks, vectors, GraphConfig(sim_threshold=0.1))

    eligible = filter_node_ids(graph, {"product_category": "coffee", "tags": ["Maintenance"]})
    results = wave_search(np.array([1, 0], dtype=np.float32), graph, vectors, top_k=2, source_k=2, steps=1, eligible_node_ids=eligible)

    assert eligible == {1}
    assert [result.node_id for result in results] == [1]
    assert filter_node_ids(graph, {"product_model": "missing"}) == set()


def test_metadata_boost_is_deterministic_after_wave_scores():
    chunks = [
        Chunk(
            "温度说明 A",
            "温度",
            ("温度",),
            1,
            1,
            "a.md",
            metadata={"manual_id": "a", "product_category": "fridge", "tags": ["temperature-setting"]},
        ),
        Chunk(
            "温度说明 B",
            "温度",
            ("温度",),
            1,
            1,
            "b.md",
            metadata={"manual_id": "b", "product_category": "fridge", "tags": ["maintenance"]},
        ),
    ]
    vectors = np.array([[0.99, 0.01], [1, 0]], dtype=np.float32)
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    graph = build_graph(chunks, vectors, GraphConfig(sim_threshold=0.0))
    query = np.array([1, 0], dtype=np.float32)

    unboosted = wave_search(query, graph, vectors, top_k=2, source_k=2, steps=0)
    boosted = wave_search(
        query,
        graph,
        vectors,
        top_k=2,
        source_k=2,
        steps=0,
        filters={"manual_id": "a", "tags": ["temperature-setting"]},
        metadata_field_boost=0.05,
        tag_boost=0.03,
    )

    assert [result.node_id for result in unboosted] == [1, 0]
    assert [result.node_id for result in boosted] == [0, 1]
