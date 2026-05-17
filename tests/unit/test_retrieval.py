from __future__ import annotations

from tagmemorag.document_assets import AssetManifest, DocumentAsset
from tagmemorag.retrieval import VisualEvidenceResolver, build_retrieve_response, detect_visual_intent, retrieve_inspect_payload
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


def _asset(asset_id="asset:sha256:p12", *, kb_name="default", doc_id="doc-1", page_number=12, status="ready"):
    return DocumentAsset(
        asset_id=asset_id,
        kb_name=kb_name,
        doc_id=doc_id,
        source_file="washer.pdf",
        source_version="v1",
        type="page_snapshot",
        mime_type="image/png",
        storage_backend="local",
        storage_key="hidden/storage/key.png",
        checksum="secret-checksum",
        page_number=page_number,
        width=100,
        height=200,
        status=status,
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
    assert evidence["assets"] == []
    assert evidence["asset_warnings"] == []
    assert payload["citations"][0]["evidence_id"] == "ev_001"
    item = payload["context_pack"]["items"][0]
    assert item["context_item_id"] == "ctx_001"
    assert item["citation_id"] == "cit_001"
    assert item["evidence_refs"] == ["ev_001"]
    assert item["asset_refs"] == []


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


def test_retrieve_inspect_payload_is_safe_and_bounded():
    payload = build_retrieve_response(
        results=[_result()],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        token_budget=100,
    )

    inspect = retrieve_inspect_payload(payload)

    assert inspect == {
        "schema_version": "retrieve_inspect.v1",
        "retrieve_id": "retrieve-1",
        "result_count": 1,
        "evidence_count": 1,
        "citation_count": 1,
        "context_item_count": 1,
        "token_budget": 100,
        "token_count_estimate": payload["context_pack"]["token_count_estimate"],
        "answerable": True,
        "fallback_reason": "",
        "selected": [
            {
                "rank": 1,
                "evidence_id": "ev_001",
                "citation_id": "cit_001",
                "context_item_id": "ctx_001",
                "doc_id": "doc-1",
                "chunk_id": "chunk-1",
                "score": 0.82,
            }
        ],
        "visual_evidence": {
            "intent": "text_answer",
            "attached_count": 0,
            "evidence_with_assets": 0,
            "omitted": {},
        },
    }
    assert "content" not in str(inspect)
    assert "Open the service panel" not in str(inspect)


def test_build_retrieve_response_attaches_page_snapshot_by_lineage():
    manifest = AssetManifest(kb_name="default", assets={"asset:sha256:p12": _asset()})

    payload = build_retrieve_response(
        results=[_result()],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        token_budget=100,
        visual_resolver=VisualEvidenceResolver(kb_name="default", manifest=manifest),
        query_text="show diagram",
    )

    asset = payload["evidence"][0]["assets"][0]
    assert asset == {
        "asset_id": "asset:sha256:p12",
        "type": "page_snapshot",
        "url": "/assets/asset%3Asha256%3Ap12?kb_name=default",
        "mime_type": "image/png",
        "page_number": 12,
        "bbox": None,
        "width": 100,
        "height": 200,
        "caption": "",
        "alt_text": "Page 12 page snapshot for citation cit_001",
        "source": {
            "doc_id": "doc-1",
            "source_file": "washer.pdf",
            "page_range": [12, 12],
        },
    }
    assert payload["context_pack"]["items"][0]["asset_refs"] == ["asset:sha256:p12"]
    assert payload["visual_evidence"] == {
        "intent": "visual_reference",
        "manifest_present": True,
        "attached_count": 1,
        "evidence_with_assets": 1,
        "omitted": {},
    }
    assert "storage_key" not in str(payload)
    assert "secret-checksum" not in str(payload)


def test_build_retrieve_response_attaches_explicit_asset_ref_and_filters_wrong_kb():
    good = _asset("asset:sha256:good", page_number=99)
    wrong_kb = _asset("asset:sha256:wrong", kb_name="other", page_number=12)
    failed = _asset("asset:sha256:failed", status="failed", page_number=12)
    manifest = AssetManifest(kb_name="default", assets={asset.asset_id: asset for asset in (good, wrong_kb, failed)})

    payload = build_retrieve_response(
        results=[_result(asset_refs=["asset:sha256:good", "asset:sha256:wrong", "asset:sha256:failed", "asset:sha256:missing"])],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        visual_resolver=VisualEvidenceResolver(kb_name="default", manifest=manifest),
    )

    evidence = payload["evidence"][0]
    assert [asset["asset_id"] for asset in evidence["assets"]] == ["asset:sha256:good"]
    assert evidence["asset_warnings"] == ["asset_wrong_kb", "asset_status_failed", "asset_ref_missing"]


def test_build_retrieve_response_missing_manifest_degrades_to_text_only():
    payload = build_retrieve_response(
        results=[_result()],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        visual_resolver=VisualEvidenceResolver(kb_name="default", manifest=None),
    )

    assert payload["evidence"][0]["assets"] == []
    assert payload["evidence"][0]["asset_warnings"] == ["asset_manifest_missing"]
    assert payload["visual_evidence"]["omitted"] == {"asset_manifest_missing": 1}


def test_detect_visual_intent_rules_are_non_ranking_metadata():
    assert detect_visual_intent("给我看按钮在哪") == "visual_reference"
    assert detect_visual_intent("Where is the reset button?") == "visual_reference"
    assert detect_visual_intent("蒸汽很小怎么办") == "text_answer"
