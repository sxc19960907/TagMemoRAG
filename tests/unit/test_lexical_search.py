from __future__ import annotations

import numpy as np

from tagmemorag.config import GraphConfig, SearchConfig, Settings
from tagmemorag.graph_builder import build_graph
from tagmemorag.lexical_search import extract_lexical_tokens, lexical_search
from tagmemorag.search_runtime import execute_search
from tagmemorag.types import Chunk
from tagmemorag.wave_searcher import wave_search


def test_extract_lexical_tokens_classifies_code_model_and_cjk_variants():
    tokens = extract_lexical_tokens("HR6FDFF701SW A-10 F 07 排水泵 and", min_token_chars=2)

    assert "hr6fdff701sw" in tokens["model"]
    assert {"a-10", "a10"} <= tokens["exact_code"]
    assert "f07" in tokens["exact_code"]
    assert "07" not in tokens["ordinary"]
    assert "排水泵" in tokens["cjk"]
    assert {"排水", "水泵"} <= tokens["cjk"]
    assert "and" not in tokens["ordinary"]


def test_lexical_search_matches_punctuation_and_cjk_terms():
    graph = build_graph(
        [
            Chunk("E-21 is shown when the 排水泵 is blocked.", "E-21 Pump Detail", ("E-21 Pump Detail",), 2, 1, "washer.md"),
            Chunk("General washer vibration advice.", "洗衣机震动", ("洗衣机震动",), 2, 2, "washer.md"),
        ],
        np.array([[1, 0], [0, 1]], dtype=np.float32),
        GraphConfig(sim_threshold=0.0),
    )

    code_matches = lexical_search(graph, "E21", candidate_k=5)
    cjk_matches = lexical_search(graph, "排水泵", candidate_k=5)

    assert code_matches[0].node_id == 0
    assert code_matches[0].mode == "exact_code"
    assert cjk_matches[0].node_id == 0


def test_lexical_search_uses_cjk_ngrams_for_partial_manual_terms():
    graph = build_graph(
        [
            Chunk("將洗衣精倒入洗劑粉盒的前區。", "洗衣粉", ("洗衣粉",), 2, 1, "washer.md"),
            Chunk("洗衣機門打開時，無法啟動機器。", "洗衣機門", ("洗衣機門",), 2, 2, "washer.md"),
        ],
        np.array([[1, 0], [0, 1]], dtype=np.float32),
        GraphConfig(sim_threshold=0.0),
    )

    matches = lexical_search(graph, "洗劑粉盒怎麼用", candidate_k=5)

    assert matches[0].node_id == 0
    assert len(matches) == 1


def test_lexical_search_rewards_multiple_ordinary_term_hits():
    graph = build_graph(
        [
            Chunk("Ionizer system dries laundry by addition of ions.", "IONIZER SYSTEM", ("IONIZER SYSTEM",), 2, 1, "dryer.md"),
            Chunk("General technical information.", "Technical information", ("Technical information",), 2, 2, "dryer.md"),
        ],
        np.array([[1, 0], [0, 1]], dtype=np.float32),
        GraphConfig(sim_threshold=0.0),
    )

    matches = lexical_search(graph, "dryer ionizer system", candidate_k=5)

    single_term_score = lexical_search(graph, "dryer ionizer", candidate_k=5)[0].score

    assert matches[0].node_id == 0
    assert matches[0].score > single_term_score


def test_lexical_search_prioritizes_specific_multi_term_manual_body():
    graph = build_graph(
        [
            Chunk("Step 2: Choosing the Cooking System", "Step 2: Choosing the Cooking System", ("Step 2",), 2, 1, "oven.md"),
            Chunk(
                "The bottom heater, the round heater, and the hot air fan operate.",
                "HOT AIR AND BOTTOM HEATER 200",
                ("Cooking systems",),
                2,
                2,
                "oven.md",
            ),
        ],
        np.array([[1, 0], [0, 1]], dtype=np.float32),
        GraphConfig(sim_threshold=0.0),
    )

    matches = lexical_search(graph, "oven cooking system hot air bottom heater", candidate_k=5)

    assert matches[0].node_id == 1


def test_lexical_search_does_not_reward_source_file_category_as_topic_hit():
    graph = build_graph(
        [
            Chunk("Display controls set the fridge and freezer temperature.", "Display controls", ("Display controls",), 2, 1, "refrigerator/manual.md"),
            Chunk("Installing Your New Appliance.", "Installing Your New Appliance", ("Installing Your New Appliance",), 2, 2, "refrigerator/manual.md"),
        ],
        np.array([[1, 0], [0, 1]], dtype=np.float32),
        GraphConfig(sim_threshold=0.0),
    )

    matches = lexical_search(graph, "refrigerator display controls", candidate_k=5)

    assert [match.node_id for match in matches] == [0]


def test_wave_search_lexical_seed_recovers_short_exact_term():
    chunks = [
        Chunk("Generic vibration advice.", "Vibration", ("Vibration",), 2, 1, "washer.md"),
        Chunk("A-10 appears when 童锁 is active.", "A-10 Child Lock", ("A-10 Child Lock",), 2, 2, "washer.md"),
    ]
    vectors = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    graph = build_graph(chunks, vectors, GraphConfig(sim_threshold=0.0))
    query = np.array([0.1, 0.0], dtype=np.float32)

    without_lexical = wave_search(query, graph, vectors, top_k=1, source_k=1, steps=0)
    with_lexical = wave_search(
        query,
        graph,
        vectors,
        top_k=1,
        source_k=1,
        steps=0,
        lexical_scores={1: 0.15},
        lexical_source_k=1,
    )

    assert without_lexical[0].node_id == 0
    assert with_lexical[0].node_id == 1


def test_execute_search_lexical_respects_filters():
    chunks = [
        Chunk(
            "A-10 appears when 童锁 is active.",
            "A-10 Child Lock",
            ("A-10 Child Lock",),
            2,
            1,
            "washer.md",
            metadata={"manual_id": "washer", "product_category": "washer"},
        ),
        Chunk(
            "童锁 phrase in a fridge troubleshooting note.",
            "Door Alarm",
            ("Door Alarm",),
            2,
            1,
            "fridge.md",
            metadata={"manual_id": "fridge", "product_category": "fridge"},
        ),
    ]
    vectors = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float32)
    graph = build_graph(chunks, vectors, GraphConfig(sim_threshold=0.0))
    cfg = Settings(search=SearchConfig(source_k=1, steps=0))

    execution = execute_search(
        state=type("State", (), {"graph": graph, "vectors": vectors, "anchors": {}, "kb_name": "default"})(),
        query_vec=np.array([1.0, 0.0], dtype=np.float32),
        settings=cfg,
        top_k=2,
        source_k=1,
        steps=0,
        decay=0.7,
        amplitude_cutoff=0.01,
        aggregate="max",
        filters={"product_category": "washer"},
        query_text="童锁",
    )

    assert [result.node_id for result in execution.results] == [0]
    assert execution.lexical_candidate_count == 1
