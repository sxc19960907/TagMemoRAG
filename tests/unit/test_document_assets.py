from __future__ import annotations

import pytest

from tagmemorag.config import AssetConfig, Settings, StorageConfig
from tagmemorag.document_assets import (
    ASSET_MANIFEST_SCHEMA_VERSION,
    DocumentAsset,
    LocalDocumentAssetStore,
    AssetManifest,
    asset_inventory_summary,
    cleanup_orphan_assets,
    extract_pdf_page_snapshots,
    load_asset_manifest,
    make_asset_id,
    remove_document_assets,
    replace_document_assets,
    save_asset_manifest,
    verify_asset_manifest,
)
from tagmemorag.errors import ServiceError
from tagmemorag.manuals import ManualMetadata
from tagmemorag.state import build_kb


def _cfg(tmp_path, **asset_overrides) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        assets=AssetConfig(root_dir=str(tmp_path / "assets"), **asset_overrides),
        model={"dim": 64},
    )


def _metadata(status: str = "active") -> ManualMetadata:
    return ManualMetadata(
        manual_id="cm1",
        title="Coffee Manual",
        source_file="coffee/cm1.pdf",
        product_category="coffee",
        version="v1",
        status=status,
    )


def _asset(asset_id: str = "asset:sha256:abc") -> DocumentAsset:
    return DocumentAsset(
        asset_id=asset_id,
        kb_name="default",
        doc_id="cm1",
        source_file="coffee/cm1.pdf",
        source_version="v1",
        type="page_snapshot",
        mime_type="image/png",
        storage_backend="local",
        storage_key="default/cm1/page_snapshot/asset-sha256-abc.png",
        checksum="abc123",
        size_bytes=3,
        page_number=1,
        width=10,
        height=20,
        status="ready",
        extractor_name="test",
        extractor_version="v1",
    )


def test_asset_manifest_round_trip_and_summary(tmp_path):
    cfg = _cfg(tmp_path)
    manifest = AssetManifest(kb_name="default", assets={"asset:sha256:abc": _asset()})

    save_asset_manifest(manifest, cfg)
    loaded = load_asset_manifest("default", cfg)

    assert loaded.schema_version == ASSET_MANIFEST_SCHEMA_VERSION
    assert loaded.assets["asset:sha256:abc"].doc_id == "cm1"
    assert asset_inventory_summary(loaded)["stats"]["by_type"] == {"page_snapshot": 1}


def test_local_asset_store_round_trip_and_safe_key(tmp_path):
    store = LocalDocumentAssetStore(tmp_path / "assets")

    ref = store.put("default", "cm1", "page_snapshot", "asset:sha256:abc", b"png", "image/png")

    assert ref.backend == "local"
    assert ref.storage_key == "default/cm1/page_snapshot/asset-sha256-abc.png"
    assert store.exists(ref.storage_key)
    assert store.get(ref.storage_key) == b"png"
    with pytest.raises(ServiceError) as exc:
        store.get("../escape.png")
    assert exc.value.code == "INVALID_INPUT"


def test_asset_id_is_stable_for_same_inputs():
    first = make_asset_id(
        kb_name="default",
        doc_id="cm1",
        source_file="coffee/cm1.pdf",
        source_version="v1",
        asset_type="page_snapshot",
        page_number=1,
        extractor_name="pymupdf",
        extractor_version="v1",
        content_checksum="abc",
    )
    second = make_asset_id(
        kb_name="default",
        doc_id="cm1",
        source_file="coffee/cm1.pdf",
        source_version="v1",
        asset_type="page_snapshot",
        page_number=1,
        extractor_name="pymupdf",
        extractor_version="v1",
        content_checksum="abc",
    )

    assert first == second
    assert first.startswith("asset:sha256:")


def test_extract_pdf_page_snapshots_degrades_when_renderer_missing(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, enabled=True, pdf_page_snapshots_enabled=True)
    pdf = tmp_path / "cm1.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setitem(__import__("sys").modules, "fitz", None)

    assets, summary = extract_pdf_page_snapshots(pdf, _metadata(), "default", cfg)

    assert summary.failed == 1
    assert summary.failure_reasons == {"renderer_unavailable": 1}
    assert assets[0].status == "failed"
    assert assets[0].failure_reason == "renderer_unavailable"


def test_build_kb_records_asset_extraction_fallback_without_breaking_search(tmp_path, fake_embedder, monkeypatch):
    cfg = _cfg(tmp_path, enabled=True, pdf_page_snapshots_enabled=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    pdf = docs / "manual.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    (docs / "manual.metadata.json").write_text(
        '{"manual_id":"cm1","title":"Coffee Manual","source_file":"manual.pdf","product_category":"coffee","version":"v1"}',
        encoding="utf-8",
    )

    class FakePage:
        def extract_text(self, *args, **kwargs):
            return "Operation\nSteam is available."

    class FakeReader:
        def __init__(self, *args, **kwargs):
            self.pages = [FakePage()]

    monkeypatch.setattr("tagmemorag.parser.PdfReader", FakeReader)
    monkeypatch.setitem(__import__("sys").modules, "fitz", None)

    state = build_kb(docs, "default", cfg, embedder=fake_embedder)

    assert state.graph.number_of_nodes() == 1
    assert state.meta["assets"]["extraction"]["failed"] == 1
    assert state.meta["assets"]["extraction"]["failure_reasons"] == {"renderer_unavailable": 1}


def test_replace_remove_verify_and_cleanup_lifecycle(tmp_path):
    store = LocalDocumentAssetStore(tmp_path / "assets")
    ref = store.put("default", "cm1", "page_snapshot", "asset:sha256:abc", b"png", "image/png")
    asset = DocumentAsset.from_dict({**_asset().to_dict(), "storage_key": ref.storage_key, "checksum": ref.checksum})
    manifest = replace_document_assets(AssetManifest("default"), "cm1", [asset])

    assert verify_asset_manifest(manifest, store)["missing_count"] == 0
    store.put("default", "cm2", "page_snapshot", "asset:sha256:orphan", b"old", "image/png")
    assert cleanup_orphan_assets(manifest, store)["deleted_count"] == 1

    deleted = remove_document_assets(manifest, "cm1", mark_deleted=True)
    assert deleted.assets[asset.asset_id].status == "deleted"
