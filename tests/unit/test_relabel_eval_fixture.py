"""Unit tests for scripts/relabel_eval_fixture.py — pure helpers, no network."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import relabel_eval_fixture as ref  # noqa: E402

from tagmemorag.types import Result  # noqa: E402


def _result(node_id: int, source_file: str, header: str, score: float = 0.5, text: str = "...") -> Result:
    return Result(
        node_id=node_id,
        score=score,
        text=text,
        header=header,
        path=[],
        source_file=source_file,
        start_line=0,
        anchor_key="",
    )


def test_make_excerpt_short_text_returns_as_is():
    assert ref._make_excerpt("hello world") == "hello world"


def test_make_excerpt_long_text_truncated_with_ellipsis():
    long = "a" * 300
    out = ref._make_excerpt(long, max_chars=50)
    assert len(out) == 50
    assert out.endswith("…")


def test_make_excerpt_collapses_newlines():
    assert ref._make_excerpt("line1\nline2\nline3") == "line1 line2 line3"


def test_parse_extra_candidates_empty():
    assert ref._parse_extra_candidates(None) == []
    assert ref._parse_extra_candidates("") == []


def test_parse_extra_candidates_single():
    assert ref._parse_extra_candidates("coffee.md:steam") == [("coffee.md", "steam")]


def test_parse_extra_candidates_multiple_with_whitespace():
    assert ref._parse_extra_candidates(" a.md:H1, b.md:H2 ,c.md:H3") == [
        ("a.md", "H1"),
        ("b.md", "H2"),
        ("c.md", "H3"),
    ]


def test_parse_extra_candidates_rejects_missing_separator():
    with pytest.raises(ValueError):
        ref._parse_extra_candidates("malformed-no-colon")


def test_dedupe_union_hashing_first_then_siliconflow():
    """Hashing results take precedence; siliconflow-only entries appended."""
    h = [
        _result(1, "a.md", "H1"),
        _result(2, "b.md", "H2"),
    ]
    s = [
        _result(2, "b.md", "H2"),  # duplicate
        _result(3, "c.md", "H3"),  # new
    ]
    # Empty graph state placeholder for extra-candidate path (not used here).
    import networkx as nx
    from tagmemorag.types import GraphState
    import numpy as np
    state = GraphState(graph=nx.Graph(), vectors=np.zeros((0, 4), dtype=np.float32), kb_name="t")

    out = ref._dedupe_union(h, s, extra_pairs=[], state=state)
    keys = [(c["source_file"], c["header"]) for c in out]
    assert keys == [("a.md", "H1"), ("b.md", "H2"), ("c.md", "H3")]
    sources = [c["source"] for c in out]
    assert sources == ["hashing", "hashing", "siliconflow"]
    # The duplicated entry retains its hashing source but records that
    # siliconflow also found it.
    b_entry = [c for c in out if c["source_file"] == "b.md"][0]
    assert "siliconflow" in b_entry.get("also_found_by", [])


def test_dedupe_union_extra_candidates_appended_last():
    h = [_result(1, "a.md", "H1")]
    s: list = []
    import networkx as nx
    from tagmemorag.types import GraphState
    import numpy as np
    g = nx.Graph()
    g.add_node(99, source_file="extra.md", header="EX1", text="extra body", tags=["t"])
    state = GraphState(graph=g, vectors=np.zeros((1, 4), dtype=np.float32), kb_name="t")

    out = ref._dedupe_union(h, s, extra_pairs=[("extra.md", "EX1")], state=state)
    assert out[-1]["source"] == "extra"
    assert out[-1]["source_file"] == "extra.md"
    assert out[-1]["node_id"] == 99
    assert out[-1]["text_excerpt"] == "extra body"


def test_dedupe_union_extra_candidate_not_in_graph_uses_placeholder():
    h: list = []
    s: list = []
    import networkx as nx
    from tagmemorag.types import GraphState
    import numpy as np
    state = GraphState(graph=nx.Graph(), vectors=np.zeros((0, 4), dtype=np.float32), kb_name="t")

    out = ref._dedupe_union(
        h, s,
        extra_pairs=[("ghost.md", "phantom")],
        state=state,
    )
    assert len(out) == 1
    assert out[0]["source"] == "extra"
    assert out[0]["node_id"] == -1
    assert "not found" in out[0]["text_excerpt"]


def test_result_to_candidate_schema():
    r = _result(7, "f.md", "H", score=0.8765432, text="body  text")
    c = ref._result_to_candidate(r, source="hashing", rank_in_source=3)
    assert c["source"] == "hashing"
    assert c["rank_in_source"] == 3
    assert c["node_id"] == 7
    assert c["source_file"] == "f.md"
    assert c["header"] == "H"
    assert c["text_excerpt"] == "body  text"
    assert c["score"] == 0.876543  # rounded to 6 dp


def test_dedupe_union_stable_sort_within_each_bucket():
    """Hashing rank 1 must come before hashing rank 2; siliconflow appended after."""
    h = [_result(1, "a.md", "H1"), _result(2, "a.md", "H2")]
    s = [_result(3, "b.md", "H1"), _result(4, "b.md", "H2")]
    import networkx as nx
    from tagmemorag.types import GraphState
    import numpy as np
    state = GraphState(graph=nx.Graph(), vectors=np.zeros((0, 4), dtype=np.float32), kb_name="t")

    out = ref._dedupe_union(h, s, extra_pairs=[], state=state)
    sources = [c["source"] for c in out]
    assert sources == ["hashing", "hashing", "siliconflow", "siliconflow"]
    ranks = [c["rank_in_source"] for c in out]
    assert ranks == [1, 2, 1, 2]
