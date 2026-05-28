from __future__ import annotations

from tagmemorag.document_assets import AssetManifest, DocumentAsset
from tagmemorag.retrieval import (
    VisualEvidenceResolver,
    VisualRetrievalResolver,
    build_retrieve_response,
    context_evidence_diagnostics,
    detect_visual_intent,
    retrieve_inspect_payload,
)
from tagmemorag.same_page_ordering import SamePageOrderingOptions
from tagmemorag.visual_retrieval.provider import DeterministicVisualCandidateProvider, NoopVisualReranker
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


def _text_result(node_id: int, score: float, text: str, chunk_id: str, section: str = ""):
    return Result(
        node_id=node_id,
        score=score,
        text=text,
        header=section or "Evidence",
        path=[section] if section else [],
        source_file="docs.md",
        start_line=node_id,
        anchor_key=f"chunk-{node_id}",
        metadata={
            "doc_id": "doc-1",
            "chunk_id": chunk_id,
            "section_path": [section] if section else [],
        },
        manual_id="doc-1",
    )


def _same_page_result(node_id: int, score: float, text: str, chunk_id: str):
    return Result(
        node_id=node_id,
        score=score,
        text=text,
        header="Hello World - GitHub Docs",
        path=["Hello World - GitHub Docs"],
        source_file="public_web/docs.github.com-en-get-started-start-your-journey-hello-world.md",
        start_line=node_id,
        anchor_key=f"chunk-{node_id}",
        metadata={
            "doc_id": "github",
            "chunk_id": chunk_id,
            "section_path": ["Hello World - GitHub Docs"],
        },
        manual_id="github",
    )


def _page_result(node_id: int, score: float, text: str, chunk_id: str, *, page: int, section: str = ""):
    result = _text_result(node_id, score, text, chunk_id, section)
    result.metadata["page_start"] = page
    result.metadata["page_end"] = page
    return result


def _asset(
    asset_id="asset:sha256:p12",
    *,
    kb_name="default",
    doc_id="doc-1",
    page_number=12,
    status="ready",
    failure_reason="",
    caption="",
    nearby_text="",
):
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
        caption=caption,
        nearby_text=nearby_text,
        status=status,
        failure_reason=failure_reason,
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
    assert evidence["provenance"] == {
        "source_format": "pdf",
        "source_file": "washer.pdf",
        "display_source": "washer.pdf",
        "page_range": [12, 13],
        "ocr": False,
        "confidence": 0.82,
    }
    assert evidence["assets"] == []
    assert evidence["asset_warnings"] == []
    assert payload["citations"][0]["evidence_id"] == "ev_001"
    item = payload["context_pack"]["items"][0]
    assert item["context_item_id"] == "ctx_001"
    assert item["citation_id"] == "cit_001"
    assert item["evidence_refs"] == ["ev_001"]
    assert item["asset_refs"] == []


def test_build_retrieve_response_expands_sparse_pdf_heading_with_adjacent_body():
    heading = Result(
        node_id=10,
        score=0.95,
        text="USING THE STEAM CLEAN FUNCTION TO",
        header="USING THE STEAM CLEAN FUNCTION TO",
        path=["USING THE STEAM CLEAN FUNCTION TO"],
        source_file="oven.pdf",
        start_line=45,
        anchor_key="heading",
        metadata={
            "doc_id": "oven",
            "chunk_id": "heading",
            "page_start": 45,
            "page_end": 45,
            "section_path": ["USING THE STEAM CLEAN FUNCTION TO"],
            "pdf_parser_profile": "product_manual",
            "pdf_header_source": "detected",
        },
        manual_id="oven",
    )
    body = Result(
        node_id=11,
        score=0.80,
        text="Turn the COOKING SYSTEM SELECTOR and TEMPERATURE KNOB to 70 C. Pour 0.6 l of water into a glass dish.",
        header="Turn the COOKING SYSTEM SELECTOR",
        path=["Turn the COOKING SYSTEM SELECTOR"],
        source_file="oven.pdf",
        start_line=45,
        anchor_key="body",
        metadata={
            "doc_id": "oven",
            "chunk_id": "body",
            "page_start": 45,
            "page_end": 45,
            "section_path": ["Turn the COOKING SYSTEM SELECTOR"],
            "pdf_parser_profile": "product_manual",
            "pdf_header_source": "detected",
        },
        manual_id="oven",
    )

    payload = build_retrieve_response(
        results=[heading, body],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        token_budget=200,
    )

    first_evidence = payload["evidence"][0]["text"]
    assert "USING THE STEAM CLEAN FUNCTION TO" in first_evidence
    assert "Pour 0.6 l of water into a glass dish" in first_evidence
    assert payload["context_pack"]["items"][0]["content"] == first_evidence


def test_build_retrieve_response_adds_safe_docx_ocr_provenance():
    result = _result(
        source_format="docx",
        remote_id="/Users/timmy/private/uploads/mixed/docx-nozzle-care.docx",
        parser_profile="pdf_ocr:product_manual",
        ocr_provider="tesseract_cli",
    )
    payload = build_retrieve_response(
        results=[result],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        token_budget=100,
    )

    provenance = payload["evidence"][0]["provenance"]
    assert provenance["source_format"] == "docx"
    assert provenance["source_file"] == "washer.pdf"
    assert provenance["original_source_file"] == "mixed/docx-nozzle-care.docx"
    assert provenance["display_source"] == "mixed/docx-nozzle-care.docx"
    assert provenance["page_range"] == [12, 13]
    assert provenance["parser_profile"] == "pdf_ocr:product_manual"
    assert provenance["ocr"] is True
    assert provenance["confidence"] == 0.82
    assert "/Users/timmy" not in str(provenance)


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


def test_same_page_ordering_disabled_preserves_result_order():
    first = _same_page_result(1, 3.2, "Create a branch and open a pull request.", "top")
    matched = _same_page_result(2, 3.1, "A repository is a folder that contains README files.", "matched")

    payload = build_retrieve_response(
        results=[first, matched],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        same_page_ordering=SamePageOrderingOptions(enabled=False),
        query_text="what is a github repository README",
    )

    assert [item["metadata"]["chunk_id"] for item in payload["results"]] == ["top", "matched"]
    assert [item["chunk_id"] for item in payload["evidence"]] == ["top", "matched"]


def test_same_page_ordering_enabled_promotes_pressure_result():
    first = _same_page_result(1, 3.2, "Create a branch and open a pull request.", "top")
    matched = _same_page_result(2, 3.1, "A repository is a folder that contains README files.", "matched")

    payload = build_retrieve_response(
        results=[first, matched],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        same_page_ordering=SamePageOrderingOptions(enabled=True),
        query_text="what is a github repository README",
    )

    assert [item["metadata"]["chunk_id"] for item in payload["results"]] == ["matched", "top"]
    assert [item["chunk_id"] for item in payload["evidence"]] == ["matched", "top"]
    assert payload["citations"][0]["evidence_id"] == "ev_001"


def test_same_page_ordering_enabled_preserves_rank_one_useful_result():
    matched = _same_page_result(1, 3.2, "A repository is a folder that contains README files.", "matched")
    later = _same_page_result(2, 2.8, "Create a branch and open a pull request.", "later")

    payload = build_retrieve_response(
        results=[matched, later],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        same_page_ordering=SamePageOrderingOptions(enabled=True),
        query_text="what is a github repository README",
    )

    assert [item["metadata"]["chunk_id"] for item in payload["results"]] == ["matched", "later"]


def test_same_page_ordering_enabled_preserves_rank_one_good_enough_result():
    first = _same_page_result(1, 3.2, "A private cache is a cache tied to a specific client and can store personalized responses.", "first")
    later = _same_page_result(2, 2.8, "A private cache is a cache tied to a specific client and should revalidate responses.", "later")

    payload = build_retrieve_response(
        results=[first, later],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        same_page_ordering=SamePageOrderingOptions(enabled=True),
        query_text="MDN HTTP caching no-cache private personalized response shared cache",
    )

    assert [item["metadata"]["chunk_id"] for item in payload["results"]] == ["first", "later"]


def test_same_page_ordering_enabled_preserves_large_rank_one_score_lead():
    first = _same_page_result(1, 3.2, "Standard deduction filing status table.", "first")
    later = _same_page_result(2, 3.0, "A deduction is available when the worksheet applies.", "later")

    payload = build_retrieve_response(
        results=[first, later],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        same_page_ordering=SamePageOrderingOptions(enabled=True),
        query_text="IRS standard deduction table filing status",
    )

    assert [item["metadata"]["chunk_id"] for item in payload["results"]] == ["first", "later"]


def test_same_page_ordering_enabled_preserves_equivalent_score_peer():
    first = _same_page_result(1, 3.2, "Hot air bottom heater cooking system.", "first")
    later = _same_page_result(2, 3.2, "Bottom heater fan cooking system.", "later")

    payload = build_retrieve_response(
        results=[first, later],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        same_page_ordering=SamePageOrderingOptions(enabled=True),
        query_text="oven cooking system hot air bottom heater",
    )

    assert [item["metadata"]["chunk_id"] for item in payload["results"]] == ["first", "later"]


def test_context_pack_prefers_complementary_evidence_under_budget():
    duplicate = "A repository is a folder with related project files."
    near_duplicate = "A repository folder stores related project files."
    complementary = "README files are written in Markdown."
    payload = build_retrieve_response(
        results=[
            _text_result(1, 0.99, duplicate, "chunk-repo-1", "Repository"),
            _text_result(2, 0.98, near_duplicate, "chunk-repo-2", "Repository"),
            _text_result(3, 0.80, complementary, "chunk-readme", "README"),
        ],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        token_budget=25,
    )

    refs = [item["evidence_refs"][0] for item in payload["context_pack"]["items"]]

    assert refs == ["ev_001", "ev_003"]


def test_context_pack_prefers_answer_bearing_evidence_for_first_slot():
    overview = "This tutorial teaches GitHub essentials like repositories, branches, commits, and pull requests."
    answer = "You can think of a repository as a folder that contains related items."
    payload = build_retrieve_response(
        results=[
            _text_result(1, 0.99, overview, "chunk-overview", "Overview"),
            _text_result(2, 0.80, answer, "chunk-answer", "Repository"),
        ],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        token_budget=30,
        query_text="GitHub repository folder",
    )

    assert [item["evidence_refs"][0] for item in payload["context_pack"]["items"]] == ["ev_002"]
    assert payload["context_pack"]["items"][0]["content"] == answer


def test_context_pack_keeps_high_rank_relevant_evidence_under_tight_budget():
    top_relevant = "Force revalidation uses the no-cache directive to validate cached responses."
    lower_definition = "No-cache means reuse requires revalidation."
    lower_related = "No-store blocks storing responses."
    payload = build_retrieve_response(
        results=[
            _text_result(1, 0.99, top_relevant, "chunk-top", "Force Revalidation"),
            _text_result(2, 0.80, lower_definition, "chunk-definition", "No-cache"),
            _text_result(3, 0.78, lower_related, "chunk-related", "No-store"),
        ],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        token_budget=30,
        query_text="no-cache directive validation revalidation",
    )

    assert [item["evidence_refs"][0] for item in payload["context_pack"]["items"]] == ["ev_002", "ev_001"]


def test_context_pack_compacts_long_context_to_query_relevant_sentences():
    long_evidence = (
        "HTTP caching overview explains browser and proxy caches. "
        "Force revalidation uses the no-cache directive to validate cached responses before reuse. "
        "Images and stylesheets may be cached for a long time. "
        "Private responses should not be shared with other users."
    )
    payload = build_retrieve_response(
        results=[_text_result(1, 0.99, long_evidence, "chunk-cache", "Caching")],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        token_budget=120,
        query_text="no-cache directive validate cached responses reuse",
    )

    content = payload["context_pack"]["items"][0]["content"]

    assert "Force revalidation uses the no-cache directive" in content
    assert "Images and stylesheets" not in content
    assert payload["context_pack"]["token_count_estimate"] < (len(long_evidence) + 3) // 4


def test_context_pack_merges_adjacent_supporting_evidence_under_budget():
    primary = "No-cache requires revalidation before reuse."
    adjacent = "No-cache permits storing responses."
    unrelated = "Images and stylesheets may be cached for a long time."
    payload = build_retrieve_response(
        results=[
            _page_result(10, 0.99, primary, "chunk-primary", page=4, section="HTTP caching"),
            _page_result(11, 0.70, adjacent, "chunk-adjacent", page=4, section="HTTP caching"),
            _page_result(20, 0.69, unrelated, "chunk-unrelated", page=9, section="HTTP caching"),
        ],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        token_budget=21,
        query_text="no-cache directive storing responses revalidation reuse",
    )

    item = payload["context_pack"]["items"][0]

    assert item["evidence_refs"] == ["ev_001", "ev_002"]
    assert item["citation_ids"] == ["cit_001", "cit_002"]
    assert "permits storing responses" in item["content"]
    assert "Images and stylesheets" not in item["content"]


def test_context_pack_compacts_lower_rank_adjacent_support_to_fit_budget():
    primary = (
        "max-age=0 and must-revalidate are older cache-control workarounds for validation. "
        "They are related to no-cache but not the clearest explanation."
    )
    adjacent = (
        "The no-store directive prevents storing a response. "
        "A no-cache directive still forces validation before reuse."
    )
    lower_rank_expected = (
        "The no-cache directive does not prevent the storing of responses. "
        "Instead, it prevents the reuse of responses without revalidation. "
        "Unrelated browser history and image cache details follow in this long paragraph."
    )
    payload = build_retrieve_response(
        results=[
            _page_result(10, 0.99, primary, "chunk-primary", page=4, section="HTTP caching"),
            _page_result(11, 0.90, adjacent, "chunk-adjacent", page=4, section="HTTP caching"),
            _page_result(12, 0.80, lower_rank_expected, "chunk-expected", page=4, section="HTTP caching"),
        ],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        token_budget=85,
        query_text="no-cache directive validation revalidation storing responses",
    )

    item = payload["context_pack"]["items"][0]

    assert item["evidence_refs"] == ["ev_001", "ev_002", "ev_003"]
    assert item["citation_ids"] == ["cit_001", "cit_002", "cit_003"]
    assert "max-age=0" in item["content"]
    assert "forces validation before reuse" in item["content"]
    assert "does not prevent the storing of responses" in item["content"]
    assert "Unrelated browser history" not in item["content"]


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


def test_context_evidence_diagnostics_explains_selected_context_without_snippets():
    payload = build_retrieve_response(
        results=[
            _text_result(1, 0.99, "Repository overview covers branches and commits.", "chunk-overview"),
            _text_result(2, 0.80, "A repository is a folder that contains related project items.", "chunk-answer"),
        ],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        token_budget=30,
        query_text="repository folder",
    )

    diagnostics = context_evidence_diagnostics(payload, query_text="repository folder")

    assert diagnostics[1]["selected"] is True
    assert diagnostics[1]["context_rank"] == 1
    assert diagnostics[1]["context_usefulness"] > diagnostics[0]["context_usefulness"]
    assert "text" not in diagnostics[0]
    assert "folder that contains" not in str(diagnostics)


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


def test_build_retrieve_response_reports_safe_failed_inferred_asset_reason():
    failed = _asset("asset:sha256:failed", status="failed", page_number=12, failure_reason="renderer_unavailable")
    manifest = AssetManifest(kb_name="default", assets={failed.asset_id: failed})

    payload = build_retrieve_response(
        results=[_result()],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        visual_resolver=VisualEvidenceResolver(kb_name="default", manifest=manifest),
    )

    evidence = payload["evidence"][0]
    assert evidence["assets"] == []
    assert evidence["asset_warnings"] == ["asset_failed_renderer_unavailable", "no_matching_assets"]
    assert "storage_key" not in str(payload)


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


def test_visual_retrieval_disabled_keeps_no_visual_candidates():
    manifest = AssetManifest(kb_name="default", assets={"asset:sha256:p12": _asset(caption="Reset button diagram")})

    payload = build_retrieve_response(
        results=[],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        visual_retrieval_resolver=VisualRetrievalResolver(
            kb_name="default",
            manifest=manifest,
            provider=DeterministicVisualCandidateProvider(),
            reranker=NoopVisualReranker(),
            enabled=False,
        ),
        query_text="show reset button",
    )

    assert payload["evidence"] == []
    assert payload["visual_evidence"]["retrieval"]["omitted"] == {"visual_retrieval_disabled": 1}


def test_visual_retrieval_adds_visual_only_evidence_for_visual_intent():
    manifest = AssetManifest(kb_name="default", assets={"asset:sha256:p12": _asset(caption="Reset button diagram", nearby_text="Hold the reset button for three seconds.")})

    payload = build_retrieve_response(
        results=[],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        visual_retrieval_resolver=VisualRetrievalResolver(
            kb_name="default",
            manifest=manifest,
            provider=DeterministicVisualCandidateProvider(),
            reranker=NoopVisualReranker(),
            enabled=True,
            max_candidates=2,
            min_score=0.1,
        ),
        query_text="show reset button",
    )

    evidence = payload["evidence"][0]
    assert evidence["content_type"] == "visual_asset"
    assert evidence["visual_candidate"]["asset_id"] == "asset:sha256:p12"
    assert evidence["assets"][0]["asset_id"] == "asset:sha256:p12"
    assert payload["context_pack"]["items"][0]["content_type"] == "visual_asset"
    assert payload["context_pack"]["items"][0]["asset_refs"] == ["asset:sha256:p12"]
    assert payload["answerability"]["answerable"] is True
    assert payload["visual_evidence"]["retrieval"]["candidate_count"] == 1
    serialized = str(payload)
    assert "hidden/storage/key" not in serialized
    assert "secret-checksum" not in serialized


def test_visual_retrieval_skips_non_visual_intent():
    manifest = AssetManifest(kb_name="default", assets={"asset:sha256:p12": _asset(caption="Reset button diagram")})

    payload = build_retrieve_response(
        results=[],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        visual_retrieval_resolver=VisualRetrievalResolver(
            kb_name="default",
            manifest=manifest,
            provider=DeterministicVisualCandidateProvider(),
            reranker=NoopVisualReranker(),
            enabled=True,
        ),
        query_text="how to clean filter",
    )

    assert payload["evidence"] == []
    assert payload["visual_evidence"]["retrieval"]["omitted"] == {"visual_intent_not_detected": 1}


def test_visual_retrieval_dedupes_assets_already_attached_to_text_evidence():
    manifest = AssetManifest(kb_name="default", assets={"asset:sha256:p12": _asset(caption="Reset button diagram")})

    payload = build_retrieve_response(
        results=[_result()],
        build_id="b1",
        kb_name="default",
        trace_id="trace-1",
        search_id="search-1",
        retrieve_id="retrieve-1",
        visual_resolver=VisualEvidenceResolver(kb_name="default", manifest=manifest),
        visual_retrieval_resolver=VisualRetrievalResolver(
            kb_name="default",
            manifest=manifest,
            provider=DeterministicVisualCandidateProvider(),
            reranker=NoopVisualReranker(),
            enabled=True,
        ),
        query_text="show reset button",
    )

    assert len(payload["evidence"]) == 1
    assert payload["evidence"][0]["assets"][0]["asset_id"] == "asset:sha256:p12"
    assert payload["visual_evidence"]["retrieval"]["omitted"] == {"no_visual_candidates": 1}
