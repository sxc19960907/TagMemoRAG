from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.config import (
    AnswerConfig,
    AssetConfig,
    GraphConfig,
    ManualLibraryConfig,
    SearchConfig,
    Settings,
    StorageConfig,
    VisualRetrievalConfig,
)
from tagmemorag.connectors.materialize import materialize_connector_records
from tagmemorag.connectors.provider import fixture_markdown_record
from tagmemorag.document_assets import (
    AssetManifest,
    DocumentAsset,
    LocalDocumentAssetStore,
    save_asset_manifest,
)
from tagmemorag.graph_builder import build_graph
from tagmemorag.manual_bundle import export_bundle, import_bundle, inspect_bundle
from tagmemorag.manual_library import list_records, load_manifest
from tagmemorag.ocr.provider import DeterministicOCRProvider
from tagmemorag.parser import parse_document_with_ocr_summary
from tagmemorag.queryplan.plan_log import _reset_shared_writer_for_tests
from tagmemorag.state import AppState, build_kb
from tagmemorag.wave_searcher import wave_search


@pytest.fixture(autouse=True)
def _reset_api_globals():
    _reset_shared_writer_for_tests()
    api._ANSWER_GENERATOR_CACHE.clear()
    api._RERANK_DISPATCHER_CACHE.clear()
    yield
    _reset_shared_writer_for_tests()
    api._ANSWER_GENERATOR_CACHE.clear()
    api._RERANK_DISPATCHER_CACHE.clear()


def _flush_plan_writer() -> None:
    from tagmemorag.queryplan.plan_log import _shared_writer

    _shared_writer().flush(timeout=2.0)


def _settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
        search=SearchConfig(metadata_narrowing_enabled=False),
        **overrides,
    )


def test_default_settings_keep_mvp_features_conservative():
    cfg = Settings()

    assert cfg.answer.enabled is False
    assert cfg.ocr.enabled is False
    assert cfg.visual_retrieval.enabled is False
    assert cfg.connectors.enabled is False
    assert cfg.reranker.enabled is False
    assert cfg.queryplan.persist_enabled is True
    assert cfg.queryplan.default_rerank_tier == "off"
    assert cfg.assets.enabled is False
    assert cfg.vector_store.provider == "npz"
    assert cfg.manual_library.registry_backend == "file"
    assert cfg.manual_library.blob_backend == "local"
    assert cfg.wave_phase1.spike_enabled is False
    assert cfg.wave_phase1.dynamic_boost_factor_strategy == "constant"


def test_connector_kb_answer_reuses_retrieve_and_persists_queryplan(tmp_path, fake_embedder):
    cfg = _settings(tmp_path, answer=AnswerConfig(enabled=True, provider="noop"))
    record = fixture_markdown_record(
        record_id="connector-reset-v1",
        manual_id="connector-reset",
        source_file="connector/reset.md",
        title="Connector Reset",
        text="# Reset Button\nHold the connector reset button for three seconds.",
    )
    materialize_connector_records(
        (record,),
        kb_name="default",
        root_dir=tmp_path / "connector_docs",
        provider="fixture",
    )
    state = build_kb(tmp_path / "connector_docs" / "default", "default", cfg, embedder=fake_embedder)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post(
        "/answer",
        json={"question": "connector reset button", "top_k": 1, "include_retrieve": True, "debug": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]["kind"] == "answer"
    assert body["answer"]["model_id"] == "noop"
    assert body["retrieve"]["answerability"]["answerable"] is True
    assert body["plan_id"] == body["retrieve"]["plan_id"]
    assert body["retrieve"]["results"][0]["manual_id"] == "connector-reset"
    assert "connector reset button" in body["retrieve"]["context_pack"]["items"][0]["content"].lower()
    assert "answer_noop_provider" in body["warnings"]

    _flush_plan_writer()
    db_path = Path(cfg.storage.data_dir) / "default" / "query_plans.db"
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT intent, evidence_ids_json, warnings_json FROM plans WHERE plan_id = ?",
            (body["plan_id"],),
        ).fetchone()
    assert row is not None
    assert row[0] == "text_answer"
    assert json.loads(row[1]) == ["ev_001"]
    assert json.loads(row[2]) == []


def test_visual_manifest_appends_safe_visual_evidence_when_enabled(tmp_path, fake_embedder):
    cfg = _settings(
        tmp_path,
        assets=AssetConfig(enabled=True, root_dir=str(tmp_path / "assets")),
        visual_retrieval=VisualRetrievalConfig(enabled=True, max_candidates=2, min_score=0.01),
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# Operation\nPlain text only.\n", encoding="utf-8")
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    store = LocalDocumentAssetStore(cfg.assets.root_dir)
    ref = store.put("default", "manual", "page_snapshot", "asset:sha256:acceptance-visual", b"png", "image/png")
    asset = DocumentAsset(
        asset_id="asset:sha256:acceptance-visual",
        kb_name="default",
        doc_id="manual",
        source_file="manual.md",
        type="page_snapshot",
        mime_type=ref.mime_type,
        storage_backend=ref.backend,
        storage_key=ref.storage_key,
        checksum=ref.checksum,
        size_bytes=ref.size_bytes,
        page_number=1,
        width=640,
        height=480,
        caption="Reset button diagram",
        nearby_text="Hold reset button for three seconds.",
        status="ready",
    )
    save_asset_manifest(AssetManifest(kb_name="default", assets={asset.asset_id: asset}), cfg)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post(
        "/retrieve",
        json={"question": "show reset button diagram", "top_k": 1, "filters": {"manual_id": "missing"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["visual_evidence"]["intent"] == "visual_reference"
    assert body["visual_evidence"]["retrieval"]["enabled"] is True
    assert body["visual_evidence"]["retrieval"]["candidate_count"] == 1
    assert body["evidence"][0]["content_type"] == "visual_asset"
    assert body["evidence"][0]["assets"][0]["asset_id"] == "asset:sha256:acceptance-visual"
    assert body["context_pack"]["items"][0]["asset_refs"] == ["asset:sha256:acceptance-visual"]
    serialized = str(body)
    assert ref.storage_key not in serialized
    assert ref.checksum not in serialized
    assert "storage_key" not in serialized
    assert "checksum" not in serialized


def test_ocr_fixture_text_can_enter_graph_search_when_enabled(tmp_path, fake_embedder, monkeypatch):
    class _FakePdfPage:
        def extract_text(self, *_args, **_kwargs):
            return ""

    class _FakePdfReader:
        def __init__(self, _path):
            self.pages = [_FakePdfPage()]

    monkeypatch.setattr("tagmemorag.parser.PdfReader", _FakePdfReader)
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    parsed = parse_document_with_ocr_summary(
        pdf,
        max_chars=500,
        min_chars=1,
        metadata={
            "manual_id": "scan",
            "title": "Scan Manual",
            "source_file": "scan.pdf",
            "product_category": "coffee",
            "ocr_pages": {"1": "Steam button label is visible beside the reset switch."},
        },
        ocr_provider=DeterministicOCRProvider(),
        ocr_enabled=True,
        kb_name="default",
    )

    assert parsed.ocr_summary.attempted == 1
    assert parsed.ocr_summary.created == 1
    embeddings = fake_embedder.encode_batch([chunk.text for chunk in parsed.chunks])
    graph = build_graph(parsed.chunks, embeddings, GraphConfig(sim_threshold=0.0))
    results = wave_search(
        fake_embedder.encode_batch(["steam button"])[0],
        graph,
        embeddings,
        top_k=1,
        source_k=1,
        steps=0,
    )

    assert len(results) == 1
    assert "Steam button label" in results[0].text
    assert results[0].metadata["ocr_source"] == "pdf_missing_text"
    assert results[0].manual_id == "scan"


def test_connector_materialization_exports_and_imports_manual_bundle(tmp_path):
    source_cfg = _bundle_cfg(tmp_path / "source")
    target_cfg = _bundle_cfg(tmp_path / "target")
    record = fixture_markdown_record(
        record_id="connector-bundle-v1",
        manual_id="connector-bundle",
        source_file="connector/bundle.md",
        title="Connector Bundle",
        text="# Bundle\nBundle round trip text.",
    )
    materialize_connector_records(
        (record,),
        kb_name="default",
        root_dir=Path(source_cfg.manual_library.root_dir),
        provider="fixture",
    )
    bundle = tmp_path / "connector.bundle.zip"

    exported = export_bundle("default", source_cfg, bundle)
    inspected = inspect_bundle(bundle, target_cfg, target_kb="restored")
    result = import_bundle(bundle, target_cfg, target_kb="restored")

    assert exported.manual_count == 1
    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("tagmemorag-bundle.json"))
        assert manifest["counts"]["manual_count"] == 1
    assert inspected.valid is True
    assert inspected.checksum_verified is True
    assert result.imported_count == 1
    records = list_records("restored", target_cfg)
    assert [record.manual_id for record in records] == ["connector-bundle"]
    restored_manifest = load_manifest("restored", target_cfg)
    assert restored_manifest.pending_changes is True
    assert restored_manifest.dirty_manuals["connector-bundle"].operation == "bundle_import"


def _bundle_cfg(root: Path) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(root / "data")),
        manual_library=ManualLibraryConfig(
            root_dir=str(root / "manuals"),
            registry_backend="file",
            registry_path=str(root / "registry.sqlite3"),
            blob_backend="local",
            blob_root_dir=str(root / "blobs"),
        ),
        model={"dim": 64},
    )
