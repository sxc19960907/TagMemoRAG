from __future__ import annotations

from tagmemorag.config import Settings, VisualRetrievalConfig
from tagmemorag.document_assets import AssetManifest, DocumentAsset
from tagmemorag.visual_retrieval.base import VisualQueryContext
from tagmemorag.visual_retrieval.provider import (
    DeterministicVisualCandidateProvider,
    NoopVisualReranker,
    create_visual_components,
)


def _asset(asset_id: str = "asset:sha256:button") -> DocumentAsset:
    return DocumentAsset(
        asset_id=asset_id,
        kb_name="default",
        doc_id="manual",
        source_file="manual.pdf",
        type="page_snapshot",
        mime_type="image/png",
        storage_backend="local",
        storage_key="hidden/key.png",
        checksum="secret",
        page_number=3,
        caption="Reset button diagram",
        nearby_text="Hold reset button for three seconds.",
        status="ready",
    )


def test_create_visual_components_disabled_returns_none():
    assert create_visual_components(Settings()) == (None, None)


def test_create_visual_components_deterministic():
    provider, reranker = create_visual_components(
        Settings(visual_retrieval=VisualRetrievalConfig(enabled=True, provider_version="fixture.v1"))
    )

    assert isinstance(provider, DeterministicVisualCandidateProvider)
    assert isinstance(reranker, NoopVisualReranker)
    assert provider.version == "fixture.v1"


def test_deterministic_provider_scores_manifest_assets():
    provider = DeterministicVisualCandidateProvider(version="fixture.v1")
    manifest = AssetManifest(kb_name="default", assets={"asset:sha256:button": _asset()})
    context = VisualQueryContext(
        query_text="show reset button",
        visual_intent="visual_reference",
        kb_name="default",
        manifest=manifest,
        max_candidates=4,
        min_score=0.1,
    )

    candidates = provider.candidates(context)

    assert len(candidates) == 1
    assert candidates[0].asset_id == "asset:sha256:button"
    assert candidates[0].score > 0
    assert candidates[0].provider == "deterministic"
    assert candidates[0].provider_version == "fixture.v1"


def test_deterministic_provider_filters_wrong_kb_and_status():
    provider = DeterministicVisualCandidateProvider()
    good = _asset("asset:sha256:good")
    wrong_kb = DocumentAsset.from_dict({**_asset("asset:sha256:wrong").to_dict(), "kb_name": "other"})
    failed = DocumentAsset.from_dict({**_asset("asset:sha256:failed").to_dict(), "status": "failed"})
    manifest = AssetManifest(kb_name="default", assets={asset.asset_id: asset for asset in (good, wrong_kb, failed)})

    candidates = provider.candidates(
        VisualQueryContext(
            query_text="reset button",
            visual_intent="visual_reference",
            kb_name="default",
            manifest=manifest,
            max_candidates=4,
            min_score=0.1,
        )
    )

    assert [candidate.asset_id for candidate in candidates] == ["asset:sha256:good"]
