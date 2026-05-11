from __future__ import annotations

from pathlib import Path

from tagmemorag.state import build_kb
from tagmemorag.wave_searcher import wave_search


def test_coffee_fixture_retrieval(test_config, fake_embedder):
    docs = Path(__file__).parents[1] / "fixtures"
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    query = fake_embedder.encode_query("蒸汽很小")
    results = wave_search(query, state.graph, state.vectors, state.anchors, top_k=5)
    text = "\n".join(result.header + result.text for result in results)
    assert "蒸汽" in text
    assert "清洗" in text
    assert "E05" in text
