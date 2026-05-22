from __future__ import annotations

from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.auth.config_store import ConfigAuthStore
from tagmemorag.cache.lru_ttl import LRUTTLCache
from tagmemorag.config import ApiKeyConfig, AssetConfig, AuthConfig, CacheConfig, OCRConfig, SearchConfig, Settings, StorageConfig, VectorStoreConfig, VisualRetrievalConfig
from tagmemorag.ocr.base import OCRPageResult
from tagmemorag.document_assets import AssetManifest, DocumentAsset, LocalDocumentAssetStore, save_asset_manifest
from tagmemorag.state import AppState, build_kb, save_kb
from tagmemorag.types import Anchor
from tests.unit.test_storage_state import FakeQdrantClient


def test_api_search_and_anchor(tmp_path, test_config, fake_embedder, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/search", json={"question": "蒸汽很小", "top_k": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["build_id"] == state.build_id
    assert body["search_id"]
    assert body["results"]
    assert "search_time_ms" in body and body["search_time_ms"] >= 0
    assert "debug" not in body

    anchor_response = client.post("/anchor", json={"node_id": 0, "label": "蒸汽重点"})
    assert anchor_response.status_code == 200
    anchor_key = anchor_response.json()["anchor_key"]
    assert client.get("/anchor").json()["anchors"][0]["anchor_key"] == anchor_key
    assert client.delete(f"/anchor/{anchor_key}").status_code == 200


def test_api_retrieve_returns_text_evidence_context_and_citations(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/retrieve", json={"question": "蒸汽很小", "top_k": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "retrieve.v1"
    assert body["build_id"] == state.build_id
    assert body["search_id"]
    assert body["retrieve_id"]
    assert body["results"]
    assert body["evidence"]
    evidence = body["evidence"][0]
    assert evidence["evidence_id"] == "ev_001"
    assert evidence["citation_id"] == "cit_001"
    assert evidence["doc_id"]
    assert evidence["chunk_id"].startswith("chunk:sha256:")
    assert evidence["matched_chunk_ids"] == [evidence["chunk_id"]]
    assert body["citations"][0]["evidence_id"] == "ev_001"
    item = body["context_pack"]["items"][0]
    assert item["context_item_id"] == "ctx_001"
    assert item["citation_id"] == "cit_001"
    assert item["evidence_refs"] == ["ev_001"]
    assert item["asset_refs"] == []
    assert body["answerability"]["answerable"] is True
    assert "debug" not in body


def test_api_retrieve_attaches_visual_assets_from_manifest(tmp_path, fake_embedder):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        assets=AssetConfig(enabled=True, root_dir=str(tmp_path / "assets")),
        model={"dim": 64},
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    chunk_metadata = dict(state.graph.nodes[0]["metadata"])
    asset = DocumentAsset(
        asset_id="asset:sha256:retrieve",
        kb_name="default",
        doc_id=str(chunk_metadata["doc_id"]),
        source_file="manual.md",
        type="page_snapshot",
        mime_type="image/png",
        storage_backend="local",
        storage_key="default/manual/page_snapshot/asset-sha256-retrieve.png",
        checksum="hidden-checksum",
        page_number=None,
        width=640,
        height=480,
        status="ready",
    )
    chunk_metadata["asset_refs"] = [asset.asset_id]
    state.graph.nodes[0]["metadata"] = chunk_metadata
    save_asset_manifest(AssetManifest(kb_name="default", assets={asset.asset_id: asset}), cfg)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/retrieve", json={"question": "给我看蒸汽按钮在哪", "top_k": 1, "debug": True})

    assert response.status_code == 200
    body = response.json()
    evidence = body["evidence"][0]
    assert [item["asset_id"] for item in evidence["assets"]] == ["asset:sha256:retrieve"]
    assert evidence["assets"][0]["url"] == "/assets/asset%3Asha256%3Aretrieve?kb_name=default"
    assert body["context_pack"]["items"][0]["asset_refs"] == ["asset:sha256:retrieve"]
    assert body["visual_evidence"]["intent"] == "visual_reference"
    assert body["debug"]["retrieve_inspect"]["visual_evidence"]["attached_count"] == 1
    serialized = str(body)
    assert "storage_key" not in serialized
    assert "hidden-checksum" not in serialized


def test_api_retrieve_visual_retrieval_can_return_visual_only_asset(tmp_path, fake_embedder):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        assets=AssetConfig(enabled=True, root_dir=str(tmp_path / "assets")),
        visual_retrieval=VisualRetrievalConfig(enabled=True, max_candidates=2),
        model={"dim": 64},
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n普通文本。\n", encoding="utf-8")
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    store = LocalDocumentAssetStore(cfg.assets.root_dir)
    ref = store.put("default", "manual", "page_snapshot", "asset:sha256:visual", b"png", "image/png")
    asset = DocumentAsset(
        asset_id="asset:sha256:visual",
        kb_name="default",
        doc_id="manual",
        source_file="manual.md",
        type="page_snapshot",
        mime_type=ref.mime_type,
        storage_backend=ref.backend,
        storage_key=ref.storage_key,
        checksum=ref.checksum,
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

    response = client.post("/retrieve", json={"question": "show reset button", "filters": {"manual_id": "missing"}})

    assert response.status_code == 200
    body = response.json()
    assert body["evidence"][0]["content_type"] == "visual_asset"
    assert body["evidence"][0]["assets"][0]["asset_id"] == "asset:sha256:visual"
    assert body["context_pack"]["items"][0]["asset_refs"] == ["asset:sha256:visual"]
    assert body["visual_evidence"]["retrieval"]["candidate_count"] == 1
    serialized = str(body)
    assert ref.storage_key not in serialized
    assert ref.checksum not in serialized


def test_api_retrieve_debug_includes_safe_inspect_payload(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/retrieve", json={"question": "蒸汽很小", "top_k": 2, "debug": True})

    assert response.status_code == 200
    inspect = response.json()["debug"]["retrieve_inspect"]
    assert inspect["schema_version"] == "retrieve_inspect.v1"
    assert inspect["retrieve_id"] == response.json()["retrieve_id"]
    assert inspect["evidence_count"] == len(response.json()["evidence"])
    assert inspect["context_item_count"] == len(response.json()["context_pack"]["items"])
    assert inspect["selected"][0]["evidence_id"] == "ev_001"
    assert inspect["selected"][0]["chunk_id"].startswith("chunk:sha256:")
    serialized = str(inspect)
    assert "蒸汽功能可以打奶泡" not in serialized
    assert "question" not in inspect
    assert "storage_key" not in serialized


def test_api_retrieve_context_budget_exhausted_is_explicit(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/retrieve", json={"question": "蒸汽", "top_k": 1, "token_budget": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["evidence"]
    assert body["context_pack"]["items"] == []
    assert body["answerability"] == {
        "answerable": False,
        "confidence": 0.0,
        "warnings": ["context_budget_exhausted"],
        "fallback_reason": "context_budget_exhausted",
    }


def test_api_retrieve_no_results_returns_insufficient_evidence(tmp_path, test_config, fake_embedder):
    cfg = test_config.model_copy(update={"search": SearchConfig(metadata_narrowing_enabled=False)})
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/retrieve", json={"question": "蒸汽", "filters": {"manual_id": "missing"}})

    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []
    assert body["evidence"] == []
    assert body["citations"] == []
    assert body["context_pack"]["items"] == []
    assert body["answerability"]["answerable"] is False
    assert body["answerability"]["fallback_reason"] == "no_results"


def test_api_retrieve_can_return_ocr_only_pdf_text(tmp_path, fake_embedder, monkeypatch):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
        ocr=OCRConfig(enabled=True, version="fixture.v1"),
    )

    class FakePdfPage:
        def extract_text(self, *args, **kwargs):
            return ""

    class FakePdfReader:
        def __init__(self, _path: str):
            self.pages = [FakePdfPage()]

    class FakeOCRProvider:
        provider_name = "fixture"
        version = "fixture.v1"

        def recognize_pdf_page(self, context):
            return OCRPageResult("Hidden drain pump filter is behind the lower cover.")

    monkeypatch.setattr("tagmemorag.parser.PdfReader", FakePdfReader)
    monkeypatch.setattr("tagmemorag.state.create_ocr_provider", lambda _cfg: FakeOCRProvider())
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "washer.pdf").write_bytes(b"%PDF fake")
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/retrieve", json={"question": "Where is the drain pump filter?", "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["answerability"]["answerable"] is True
    assert "Hidden drain pump filter" in body["context_pack"]["items"][0]["content"]
    assert body["results"][0]["metadata"]["ocr_provider"] == "fixture"
    assert body["results"][0]["metadata"]["ocr_version"] == "fixture.v1"


def test_api_search_debug_request_includes_operator_metadata(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/search", json={"question": "蒸汽很小", "top_k": 2, "debug": True})

    assert response.status_code == 200
    body = response.json()
    assert body["debug"] == {
        "search_strategy": "exact_local",
        "ann_enabled": False,
        "ann_candidate_count": 0,
        "ann_fallback_reason": "",
        "lexical_enabled": True,
        "lexical_candidate_count": 1,
        "lexical_source_count": 1,
        "lexical_profile": "source_boost",
        "source_k": test_config.search.source_k,
        "steps": test_config.search.steps,
        "aggregate": test_config.search.aggregate,
        "eligible_node_count": state.graph.number_of_nodes(),
        "legacy_tag_boost_disabled": False,
        "metadata_narrowing": {
            "enabled": True,
            "mode": "none",
            "detected": [],
            "hard_filters": {},
            "boost_filters": {},
            "before_count": state.graph.number_of_nodes(),
            "after_count": None,
            "fallback_reason": "",
        },
    }
    assert not {"trace_id", "search_id", "question", "candidate_ids"} & set(body["debug"])


def test_api_search_shape_does_not_include_visual_evidence(tmp_path, fake_embedder):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        assets=AssetConfig(enabled=True, root_dir=str(tmp_path / "assets")),
        model={"dim": 64},
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/search", json={"question": "蒸汽很小", "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    assert "evidence" not in body
    assert "visual_evidence" not in body


def test_api_search_config_debug_and_cache_shapes_do_not_cross(tmp_path, fake_embedder):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
        search=SearchConfig(debug_metadata_enabled=True),
        cache=CacheConfig(enabled=True, max_entries=100, ttl_seconds=3600),
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    app_state = AppState(state)
    app_state.query_cache = LRUTTLCache(cfg.cache.max_entries, cfg.cache.ttl_seconds, now_fn=lambda: 1000.0)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = app_state
    client = TestClient(api.app)

    first_debug = client.post("/search", json={"question": "蒸汽很小", "top_k": 2}).json()
    second_debug = client.post("/search", json={"question": "  蒸汽很小  ", "top_k": 2}).json()
    cfg.search.debug_metadata_enabled = False
    first_plain = client.post("/search", json={"question": "蒸汽很小", "top_k": 2}).json()
    second_plain = client.post("/search", json={"question": "  蒸汽很小  ", "top_k": 2}).json()

    assert first_debug["cache"] == "miss"
    assert second_debug["cache"] == "hit"
    assert "debug" in second_debug
    assert first_plain["cache"] == "miss"
    assert second_plain["cache"] == "hit"
    assert "debug" not in first_plain
    assert "debug" not in second_plain
    assert first_debug["search_id"] != first_plain["search_id"]


def test_api_search_accepts_steps_decay_override(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post(
        "/search",
        json={"question": "蒸汽", "top_k": 2, "steps": 0, "decay": 0.5, "aggregate": "sum"},
    )
    assert response.status_code == 200
    assert response.json()["results"]


def test_api_search_filters_by_manual_metadata(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    (docs / "fridge").mkdir(parents=True)
    (docs / "coffee").mkdir()
    (docs / "fridge" / "manual.md").write_text("# 温度\n冷藏室温度可以调节。\n", encoding="utf-8")
    (docs / "fridge" / "manual.metadata.json").write_text(
        '{"manual_id":"fridge-manual","title":"Fridge Manual","source_file":"fridge/manual.md","product_category":"fridge","product_model":"NRK6192","language":"zh-CN","tags":["temperature-setting"]}',
        encoding="utf-8",
    )
    (docs / "coffee" / "manual.md").write_text("# 温度\n咖啡温度和蒸汽设置。\n", encoding="utf-8")
    (docs / "coffee" / "manual.metadata.json").write_text(
        '{"manual_id":"coffee-manual","title":"Coffee Manual","source_file":"coffee/manual.md","product_category":"coffee","product_model":"CM1","language":"zh-CN","tags":["maintenance"]}',
        encoding="utf-8",
    )
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post(
        "/search",
        json={
            "question": "温度",
            "top_k": 5,
            "filters": {"product_category": "fridge", "product_model": "NRK6192", "tags": ["Temperature Setting"]},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"]
    assert {result["manual_id"] for result in body["results"]} == {"fridge-manual"}

    no_match = client.post("/search", json={"question": "温度", "filters": {"product_model": "missing"}})
    assert no_match.status_code == 200
    assert no_match.json()["results"] == []


def test_api_search_auto_narrows_by_model_metadata(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    (docs / "fridge").mkdir(parents=True)
    (docs / "coffee").mkdir()
    (docs / "fridge" / "manual.md").write_text("# 温度\n冷藏室温度可以调节。\n", encoding="utf-8")
    (docs / "fridge" / "manual.metadata.json").write_text(
        '{"manual_id":"fridge-manual","title":"Fridge Manual","source_file":"fridge/manual.md","brand":"Gorenje","product_category":"fridge","product_model":"NRK6192","language":"zh-CN","tags":["temperature-setting"]}',
        encoding="utf-8",
    )
    (docs / "coffee" / "manual.md").write_text("# 温度\n咖啡温度和蒸汽设置。\n", encoding="utf-8")
    (docs / "coffee" / "manual.metadata.json").write_text(
        '{"manual_id":"coffee-manual","title":"Coffee Manual","source_file":"coffee/manual.md","brand":"Acme","product_category":"coffee","product_model":"CM1","language":"zh-CN","tags":["maintenance"]}',
        encoding="utf-8",
    )
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/search", json={"question": "NRK6192 温度怎么调", "top_k": 5, "debug": True})

    assert response.status_code == 200
    body = response.json()
    assert body["results"]
    assert {result["manual_id"] for result in body["results"]} == {"fridge-manual"}
    assert body["debug"]["metadata_narrowing"]["mode"] == "hard_filter"
    assert body["debug"]["metadata_narrowing"]["hard_filters"] == {"product_model": "NRK6192"}
    assert body["debug"]["metadata_narrowing"]["after_count"] == 1


def test_api_manuals_lists_metadata_facets(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    (docs / "fridge").mkdir(parents=True)
    (docs / "fridge" / "manual.md").write_text("# 温度\n冷藏室温度可以调节。\n# 维护\n清理排水孔。\n", encoding="utf-8")
    (docs / "fridge" / "manual.metadata.json").write_text(
        '{"manual_id":"fridge-manual","title":"Fridge Manual","source_file":"fridge/manual.md","brand":"Gorenje","product_category":"fridge","product_model":"NRK6192","language":"zh-CN","tags":["temperature-setting","maintenance"]}',
        encoding="utf-8",
    )
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.get("/manuals")

    assert response.status_code == 200
    body = response.json()
    assert body["kb_name"] == "default"
    assert body["manuals"] == [
        {
            "manual_id": "fridge-manual",
            "title": "Fridge Manual",
            "source_file": "fridge/manual.md",
            "brand": "Gorenje",
            "product_category": "fridge",
            "product_name": "",
            "product_model": "NRK6192",
            "language": "zh-CN",
            "version": "",
            "tags": ["temperature-setting", "maintenance"],
            "chunk_count": 2,
        }
    ]
    assert body["facets"]["brand"] == ["Gorenje"]
    assert body["facets"]["product_category"] == ["fridge"]
    assert body["facets"]["tags"] == ["maintenance", "temperature-setting"]


def test_api_asset_endpoint_serves_ready_asset_with_kb_auth(tmp_path, fake_embedder):
    secret = "tmr_live_asset"
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        assets=AssetConfig(enabled=True, root_dir=str(tmp_path / "assets")),
        auth=AuthConfig(
            enabled=True,
            keys=[
                ApiKeyConfig(
                    id="searcher",
                    hash=ConfigAuthStore.hash_plaintext(secret),
                    kb_allowlist=["default"],
                    scopes=["search"],
                )
            ],
        ),
        model={"dim": 64},
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    store = LocalDocumentAssetStore(cfg.assets.root_dir)
    ref = store.put("default", "manual", "page_snapshot", "asset:sha256:test", b"png", "image/png")
    asset = DocumentAsset(
        asset_id="asset:sha256:test",
        kb_name="default",
        doc_id="manual",
        source_file="manual.md",
        type="page_snapshot",
        mime_type="image/png",
        storage_backend="local",
        storage_key=ref.storage_key,
        checksum=ref.checksum,
        size_bytes=ref.size_bytes,
        status="ready",
    )
    save_asset_manifest(AssetManifest(kb_name="default", assets={asset.asset_id: asset}), cfg)
    api.settings = cfg
    api.embedder = fake_embedder
    app_state = AppState(state)
    app_state.auth_store = ConfigAuthStore.from_config(cfg.auth)
    api.app_state = app_state
    client = TestClient(api.app)

    response = client.get("/assets/asset:sha256:test?kb_name=default", headers={"Authorization": f"Bearer {secret}"})

    assert response.status_code == 200
    assert response.content == b"png"
    assert response.headers["x-document-asset-id"] == "asset:sha256:test"


def test_api_asset_endpoint_rejects_wrong_kb_allowlist(tmp_path, fake_embedder):
    secret = "tmr_live_asset"
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        assets=AssetConfig(enabled=True, root_dir=str(tmp_path / "assets")),
        auth=AuthConfig(
            enabled=True,
            keys=[
                ApiKeyConfig(
                    id="searcher",
                    hash=ConfigAuthStore.hash_plaintext(secret),
                    kb_allowlist=["other"],
                    scopes=["search"],
                )
            ],
        ),
        model={"dim": 64},
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    api.settings = cfg
    app_state = AppState(state)
    app_state.auth_store = ConfigAuthStore.from_config(cfg.auth)
    api.app_state = app_state
    client = TestClient(api.app)

    response = client.get("/assets/asset:sha256:test?kb_name=default", headers={"Authorization": f"Bearer {secret}"})

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_api_anchor_add_invalid_node_returns_400(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/anchor", json={"node_id": 999, "label": "bad"})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_INPUT"


def test_api_unexpected_exception_wrapped_as_internal(tmp_path, test_config, fake_embedder, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app, raise_server_exceptions=False)

    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(api, "execute_search", boom)
    response = client.post("/search", json={"question": "x"})
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "INTERNAL"
    assert set(body) == {"code", "message", "detail"}


def test_api_error_format_when_kb_not_loaded(test_config, fake_embedder):
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState()
    client = TestClient(api.app)

    response = client.post("/search", json={"question": "蒸汽很小"})
    assert response.status_code == 404
    assert response.json()["code"] == "KB_NOT_LOADED"
    assert set(response.json()) == {"code", "message", "detail"}


def test_api_rebuild_and_graph_info(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState()
    client = TestClient(api.app)

    response = client.post("/rebuild", json={"docs_dir": str(docs)})
    assert response.status_code == 202
    task_id = response.json()["task_id"]
    for _ in range(50):
        task = client.get(f"/rebuild/{task_id}").json()
        if task["status"] != "running":
            break
    assert task["status"] == "done"
    info = client.get("/graph_info").json()
    assert info["node_count"] == 2
    assert info["build_id"]


def test_api_search_uses_ann_preselection_with_qdrant(monkeypatch, tmp_path, test_config, fake_embedder):
    FakeQdrantClient.reset()
    monkeypatch.setattr("tagmemorag.storage.qdrant_vector.QdrantVectorStore._create_client", lambda *args, **kwargs: FakeQdrantClient())
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    cfg = test_config.model_copy(update={"vector_store": VectorStoreConfig(provider="qdrant", collection_prefix="test")})
    cfg.search.ann_preselect_enabled = True
    cfg.search.ann_candidate_k = 1
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    save_kb(state, cfg)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/search", json={"question": "蒸汽很小", "top_k": 2, "debug": True})

    assert response.status_code == 200
    body = response.json()
    assert body["results"]
    assert body["debug"]["search_strategy"] == "ann_preselect_then_wave"
    assert body["debug"]["ann_enabled"] is True
    assert body["debug"]["ann_candidate_count"] == 1
    assert body["debug"]["ann_fallback_reason"] == ""


def test_api_search_ann_falls_back_on_qdrant_failure(monkeypatch, tmp_path, test_config, fake_embedder):
    FakeQdrantClient.reset()
    monkeypatch.setattr("tagmemorag.storage.qdrant_vector.QdrantVectorStore._create_client", lambda *args, **kwargs: FakeQdrantClient())
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    cfg = test_config.model_copy(update={"vector_store": VectorStoreConfig(provider="qdrant", collection_prefix="test")})
    cfg.search.ann_preselect_enabled = True
    cfg.search.ann_candidate_k = 2
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    save_kb(state, cfg)
    FakeQdrantClient.fail_next_search = True
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/search", json={"question": "蒸汽很小", "top_k": 2, "debug": True})

    assert response.status_code == 200
    body = response.json()
    assert body["results"]
    assert body["debug"]["search_strategy"] == "exact_local"
    assert body["debug"]["ann_enabled"] is True
    assert body["debug"]["ann_candidate_count"] == 0
    assert body["debug"]["ann_fallback_reason"] == "ann_query_failed"


def test_api_search_ann_keeps_filtered_results_inside_metadata_scope(monkeypatch, tmp_path, test_config, fake_embedder):
    FakeQdrantClient.reset()
    monkeypatch.setattr("tagmemorag.storage.qdrant_vector.QdrantVectorStore._create_client", lambda *args, **kwargs: FakeQdrantClient())
    docs = tmp_path / "docs"
    (docs / "fridge").mkdir(parents=True)
    (docs / "coffee").mkdir()
    (docs / "fridge" / "manual.md").write_text("# 温度\n冷藏室温度可以调节。\n", encoding="utf-8")
    (docs / "fridge" / "manual.metadata.json").write_text(
        '{"manual_id":"fridge-manual","title":"Fridge Manual","source_file":"fridge/manual.md","product_category":"fridge","product_model":"NRK6192","tags":["temperature-setting"]}',
        encoding="utf-8",
    )
    (docs / "coffee" / "manual.md").write_text("# 温度\n咖啡温度和蒸汽设置。\n", encoding="utf-8")
    (docs / "coffee" / "manual.metadata.json").write_text(
        '{"manual_id":"coffee-manual","title":"Coffee Manual","source_file":"coffee/manual.md","product_category":"coffee","product_model":"CM1","tags":["maintenance"]}',
        encoding="utf-8",
    )
    cfg = test_config.model_copy(update={"vector_store": VectorStoreConfig(provider="qdrant", collection_prefix="test")})
    cfg.search.ann_preselect_enabled = True
    cfg.search.ann_candidate_k = 2
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    save_kb(state, cfg)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post(
        "/search",
        json={
            "question": "温度",
            "top_k": 5,
            "filters": {"product_category": "fridge", "product_model": "NRK6192", "tags": ["Temperature Setting"]},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"]
    assert {result["manual_id"] for result in body["results"]} == {"fridge-manual"}


def test_api_search_ann_force_includes_eligible_anchor_when_truncated(monkeypatch, tmp_path, test_config, fake_embedder):
    FakeQdrantClient.reset()
    monkeypatch.setattr("tagmemorag.storage.qdrant_vector.QdrantVectorStore._create_client", lambda *args, **kwargs: FakeQdrantClient())
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text(
        "# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n# 故障\nE05 表示蒸汽异常。\n",
        encoding="utf-8",
    )
    cfg = test_config.model_copy(update={"vector_store": VectorStoreConfig(provider="qdrant", collection_prefix="test")})
    cfg.search.ann_preselect_enabled = True
    cfg.search.ann_candidate_k = 1
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    target_node_id = next(node_id for node_id, node in state.graph.nodes(data=True) if "E05" in str(node.get("text", "")))
    state.anchors[target_node_id] = state.anchors.get(target_node_id) or Anchor(
        anchor_key=state.graph.nodes[target_node_id]["anchor_key"],
        label="故障重点",
        boost=5.0,
        node_id=target_node_id,
    )
    save_kb(state, cfg)
    collection = FakeQdrantClient.collections["test_default"]
    collection[target_node_id].vector = [0.0 for _ in collection[target_node_id].vector]
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    client = TestClient(api.app)

    response = client.post("/search", json={"question": "蒸汽", "top_k": 3, "steps": 0, "source_k": 3})

    assert response.status_code == 200
    result_ids = {result["node_id"] for result in response.json()["results"]}
    assert target_node_id in result_ids
