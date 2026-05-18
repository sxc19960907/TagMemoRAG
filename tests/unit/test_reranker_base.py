"""Tests for reranker base dataclasses + NoopReranker (T3 Slice 1)."""

from __future__ import annotations

import pytest

from tagmemorag.reranker import (
    NoopReranker,
    RerankDoc,
    RerankResult,
    RerankResultItem,
    RerankSpec,
    RerankerOutcome,
)


# ---------- dataclasses ----------

def test_rerank_doc_frozen():
    d = RerankDoc(chunk_id="c1", text="hello")
    with pytest.raises((AttributeError, Exception)):
        d.text = "modified"  # type: ignore[misc]


def test_rerank_result_to_dict():
    r = RerankResult(
        items=(
            RerankResultItem(chunk_id="c1", raw_score=2.5, calibrated_score=1.0),
            RerankResultItem(chunk_id="c2", raw_score=1.0, calibrated_score=0.5),
        ),
        truncated_chunk_ids=("c3",),
        vendor_used="qwen3-reranker-0.6b@siliconflow",
        cache_status="miss",
        latency_ms=120,
        warnings=("retry_used",),
    )
    d = r.to_dict()
    assert d["vendor_used"] == "qwen3-reranker-0.6b@siliconflow"
    assert d["cache_status"] == "miss"
    assert d["latency_ms"] == 120
    assert len(d["items"]) == 2
    assert d["items"][0]["chunk_id"] == "c1"
    assert d["items"][0]["raw_score"] == 2.5
    assert d["items"][0]["calibrated_score"] == 1.0
    assert d["truncated_chunk_ids"] == ["c3"]
    assert d["warnings"] == ["retry_used"]


def test_rerank_spec_to_dict():
    s = RerankSpec(
        reranker_id="qwen3-reranker-0.6b@siliconflow",
        reranker_version="v1",
        instruction="Sort by relevance",
        top_n=20,
    )
    d = s.to_dict()
    assert d == {
        "reranker_id": "qwen3-reranker-0.6b@siliconflow",
        "reranker_version": "v1",
        "instruction": "Sort by relevance",
        "top_n": 20,
    }


def test_rerank_spec_no_instruction():
    s = RerankSpec(
        reranker_id="x",
        reranker_version="v1",
        instruction=None,
        top_n=10,
    )
    assert s.instruction is None


# ---------- NoopReranker ----------

def test_noop_reranker_attributes():
    n = NoopReranker()
    assert n.id == "noop"
    assert n.version == "v1"
    assert n.supports_instruction is False


def test_noop_reranker_preserves_input_order_via_descending_scores():
    n = NoopReranker()
    docs = [
        RerankDoc(chunk_id="c1", text="a"),
        RerankDoc(chunk_id="c2", text="b"),
        RerankDoc(chunk_id="c3", text="c"),
    ]
    outcome = n.rerank("q", docs, instruction=None, budget_ms=1000)
    chunk_ids = [item[0] for item in outcome.items]
    scores = [item[1] for item in outcome.items]
    assert chunk_ids == ["c1", "c2", "c3"]
    # Scores must be strictly descending so a sort-by-score keeps order
    assert scores[0] > scores[1] > scores[2] > 0


def test_noop_reranker_handles_empty():
    n = NoopReranker()
    outcome = n.rerank("q", [], instruction=None, budget_ms=1000)
    assert outcome.items == ()
    assert outcome.truncated_chunk_ids == ()


def test_noop_reranker_no_truncation():
    n = NoopReranker()
    docs = [RerankDoc(chunk_id="c1", text="a" * 100000)]  # huge
    outcome = n.rerank("q", docs, instruction=None, budget_ms=1000)
    # Noop never truncates; truncation is a vendor concern
    assert outcome.truncated_chunk_ids == ()


def test_noop_outcome_vendor_id():
    n = NoopReranker()
    outcome = n.rerank("q", [], instruction=None, budget_ms=1000)
    assert outcome.vendor_id == "noop"


# ---------- Protocol shape ----------

def test_noop_satisfies_reranker_protocol():
    """NoopReranker has all attributes/methods the Protocol expects."""
    from tagmemorag.reranker.base import Reranker
    n = NoopReranker()
    # duck-type check
    assert hasattr(n, "id")
    assert hasattr(n, "version")
    assert hasattr(n, "max_seq_length")
    assert hasattr(n, "supports_instruction")
    assert callable(n.rerank)
