from __future__ import annotations

from tagmemorag.retrieval import build_retrieve_response
from tagmemorag.types import Result


def _result(**metadata):
    return Result(
        node_id=3,
        score=0.82,
        text="Open the service panel and rinse the lower filter.",
        header="Filter cleaning",
        path=["Maintenance", "Filter cleaning"],
        source_file="washer.pdf",
        start_line=12,
        anchor_key="abc",
        metadata={
            "doc_id": "doc-1",
            "chunk_id": "chunk-1",
            "page_start": 12,
            "page_end": 13,
            "section_path": ["Maintenance", "Filter cleaning"],
            **metadata,
        },
        manual_id="manual-1",
    )


def test_build_retrieve_response_shapes_text_evidence_and_context():
    payload = build_retrieve_response(
        results=[_result()],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        token_budget=100,
        search_time_ms=1.23,
    )

    assert payload["schema_version"] == "retrieve.v1"
    assert payload["answerability"] == {
        "answerable": True,
        "confidence": 0.82,
        "warnings": [],
        "fallback_reason": "",
    }
    evidence = payload["evidence"][0]
    assert evidence["evidence_id"] == "ev_001"
    assert evidence["citation_id"] == "cit_001"
    assert evidence["doc_id"] == "doc-1"
    assert evidence["chunk_id"] == "chunk-1"
    assert evidence["page_range"] == [12, 13]
    assert evidence["section_path"] == ["Maintenance", "Filter cleaning"]
    assert payload["citations"][0]["evidence_id"] == "ev_001"
    item = payload["context_pack"]["items"][0]
    assert item["context_item_id"] == "ctx_001"
    assert item["citation_id"] == "cit_001"
    assert item["evidence_refs"] == ["ev_001"]


def test_build_retrieve_response_no_results_is_insufficient_evidence():
    payload = build_retrieve_response(
        results=[],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
    )

    assert payload["evidence"] == []
    assert payload["citations"] == []
    assert payload["context_pack"]["items"] == []
    assert payload["answerability"] == {
        "answerable": False,
        "confidence": 0.0,
        "warnings": ["no_results"],
        "fallback_reason": "no_results",
    }


def test_build_retrieve_response_context_budget_exhausted():
    payload = build_retrieve_response(
        results=[_result()],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        token_budget=1,
    )

    assert payload["context_pack"]["items"] == []
    assert payload["answerability"] == {
        "answerable": False,
        "confidence": 0.0,
        "warnings": ["context_budget_exhausted"],
        "fallback_reason": "context_budget_exhausted",
    }
