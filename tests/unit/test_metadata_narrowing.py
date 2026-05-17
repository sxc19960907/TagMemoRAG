from __future__ import annotations

import networkx as nx

from tagmemorag.metadata_narrowing import (
    MetadataIndex,
    infer_metadata_narrowing,
    merge_inferred_filters,
)


def _graph() -> nx.Graph:
    graph = nx.Graph()
    graph.add_node(
        0,
        metadata={
            "doc_id": "hisense-hr6fdff701sw-zh-cn-v1",
            "manual_id": "hisense-hr6fdff701sw-zh-cn-v1",
            "domain": "product_manual",
            "doc_type": "manual",
            "brand": "Hisense",
            "product_category": "refrigerator",
            "product_model": "HR6FDFF701SW",
            "language": "zh-CN",
            "tags": ["category:refrigerator", "model:hr6fdff701sw"],
            "attributes": {"brand": "Hisense", "product_model": "HR6FDFF701SW"},
        },
    )
    graph.add_node(
        1,
        metadata={
            "doc_id": "hisense-dhga901nl-zh-cn-v1",
            "manual_id": "hisense-dhga901nl-zh-cn-v1",
            "domain": "product_manual",
            "doc_type": "manual",
            "brand": "Hisense",
            "product_category": "dryer",
            "product_model": "DHGA901NL",
            "language": "zh-CN",
            "tags": ["category:dryer", "model:dhga901nl"],
            "attributes": {"brand": "Hisense", "product_model": "DHGA901NL"},
        },
    )
    graph.add_edge(0, 1, weight=0.5, kind="semantic")
    return graph


def test_metadata_index_looks_up_legacy_and_attribute_fields():
    index = MetadataIndex.from_graph(_graph())

    model = index.lookup("product_model", "hr6fdff701sw")
    attr_model = index.lookup("attributes.product_model", "HR6FDFF701SW")
    category_alias_hits = index.hits_for_alias("冰箱")

    assert model is not None
    assert model.node_ids == frozenset({0})
    assert attr_model is not None
    assert attr_model.doc_ids == frozenset({"hisense-hr6fdff701sw-zh-cn-v1"})
    assert [hit.value for hit in category_alias_hits] == ["refrigerator"]


def test_infer_metadata_narrowing_hard_filters_exact_model():
    decision = infer_metadata_narrowing(
        query_text="HR6FDFF701SW 制冰机怎么设置",
        graph=_graph(),
    )

    assert decision.mode == "hard_filter"
    assert decision.hard_filters == {"product_model": "HR6FDFF701SW"}
    assert decision.after_count == 1
    assert decision.detected[0].type == "product_model"


def test_infer_metadata_narrowing_hard_filters_category_alias():
    decision = infer_metadata_narrowing(
        query_text="冰箱噪音怎么处理",
        graph=_graph(),
    )

    assert decision.mode == "hard_filter"
    assert decision.hard_filters == {"product_category": "refrigerator"}
    assert decision.after_count == 1


def test_explicit_filter_conflict_prevents_inferred_hard_filter():
    decision = infer_metadata_narrowing(
        query_text="HR6FDFF701SW 制冰机怎么设置",
        graph=_graph(),
        explicit_filters={"product_model": "DHGA901NL"},
    )

    assert decision.hard_filters == {}
    assert decision.fallback_reason == "conflicts_with_explicit_filter:product_model"


def test_merge_inferred_filters_preserves_explicit_and_adds_safe_hard_filters():
    decision = infer_metadata_narrowing(
        query_text="冰箱噪音怎么处理",
        graph=_graph(),
        explicit_filters={"language": "zh-CN"},
    )

    merged = merge_inferred_filters({"language": "zh-CN"}, decision)

    assert merged == {"language": "zh-CN", "product_category": "refrigerator"}


def test_no_entity_match_keeps_mode_none():
    decision = infer_metadata_narrowing(query_text="普通维护问题", graph=_graph())

    assert decision.mode == "none"
    assert decision.hard_filters == {}
    assert decision.detected == ()
