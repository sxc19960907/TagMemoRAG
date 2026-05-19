from __future__ import annotations

import json
from types import SimpleNamespace
import time
import threading

import numpy as np
import pytest

from tagmemorag.config import OCRConfig, Settings, StorageConfig, VectorStoreConfig
from tagmemorag.graph_builder import build_graph
from tagmemorag.errors import RebuildInProgressError
from tagmemorag.qdrant_ops import inspect_qdrant
from tagmemorag.parser import parse_document
from tagmemorag.ocr.base import OCRPageResult
from tagmemorag.state import AppState, build_kb, load_kb, save_kb
from tagmemorag.storage.atomic import atomic_write
from tagmemorag.storage.json_anchor import JsonAnchorStore
from tagmemorag.storage.json_graph import JsonGraphStore
from tagmemorag.storage.npz_vector import NpzVectorStore
from tagmemorag.storage.qdrant_vector import QdrantVectorStore, collection_name
from tagmemorag.types import Anchor, Chunk


class FakeQdrantClient:
    collections: dict[str, dict[int, SimpleNamespace]] = {}
    upsert_calls: list[tuple[str, list[int]]] = []
    set_payload_calls: list[tuple[str, list[int], dict]] = []
    batch_payload_calls: list[tuple[str, list[tuple[int, dict]]]] = []
    delete_calls: list[tuple[str, list[int]]] = []
    search_calls: list[tuple[str, int, list[int]]] = []
    fail_next_upsert: bool = False
    fail_next_batch_payload: bool = False
    fail_next_search: bool = False

    def __init__(self, **_kwargs):
        pass

    @classmethod
    def reset(cls):
        cls.collections = {}
        cls.upsert_calls = []
        cls.set_payload_calls = []
        cls.batch_payload_calls = []
        cls.delete_calls = []
        cls.search_calls = []
        cls.fail_next_upsert = False
        cls.fail_next_batch_payload = False
        cls.fail_next_search = False

    def get_collection(self, collection_name):
        if collection_name not in self.collections:
            raise KeyError(collection_name)
        return {"name": collection_name}

    def create_collection(self, collection_name, vectors_config):
        self.collections[collection_name] = {}
        self.vectors_config = vectors_config

    def upsert(self, collection_name, points):
        if self.fail_next_upsert:
            type(self).fail_next_upsert = False
            raise RuntimeError("upsert failed")
        self.upsert_calls.append((collection_name, [int(point.id) for point in points]))
        collection = self.collections.setdefault(collection_name, {})
        for point in points:
            collection[int(point.id)] = SimpleNamespace(
                id=int(point.id),
                vector=list(point.vector),
                payload=dict(point.payload or {}),
            )

    def delete(self, collection_name, points_selector):
        ids = [int(node_id) for node_id in points_selector]
        self.delete_calls.append((collection_name, ids))
        collection = self.collections.setdefault(collection_name, {})
        for node_id in ids:
            collection.pop(node_id, None)

    def set_payload(self, collection_name, payload, points):
        ids = [int(node_id) for node_id in points]
        safe_payload = dict(payload)
        self.set_payload_calls.append((collection_name, ids, safe_payload))
        collection = self.collections.setdefault(collection_name, {})
        for node_id in ids:
            if node_id in collection:
                collection[node_id].payload.update(safe_payload)

    def batch_update_points(self, collection_name, update_operations):
        if self.fail_next_batch_payload:
            type(self).fail_next_batch_payload = False
            raise RuntimeError("batch payload failed")
        updates: list[tuple[int, dict]] = []
        collection = self.collections.setdefault(collection_name, {})
        for operation in update_operations:
            raw = operation["set_payload"] if isinstance(operation, dict) else operation.set_payload
            payload = dict(raw["payload"] if isinstance(raw, dict) else raw.payload)
            points = raw["points"] if isinstance(raw, dict) else raw.points
            if points is None:
                raise RuntimeError("fake batch payload requires explicit point ids")
            for node_id in points:
                point_id = int(node_id)
                updates.append((point_id, payload))
                if point_id in collection:
                    collection[point_id].payload.update(payload)
        self.batch_payload_calls.append((collection_name, updates))

    def search(self, collection_name, query_vector, limit=10, with_payload=False, with_vectors=False):
        if self.fail_next_search:
            type(self).fail_next_search = False
            raise RuntimeError("search failed")
        collection = self.collections.get(collection_name, {})
        query = np.asarray(query_vector, dtype=np.float32)
        scored = []
        for node_id, record in collection.items():
            vector = np.asarray(record.vector, dtype=np.float32)
            scored.append(SimpleNamespace(id=int(node_id), score=float(vector @ query)))
        scored.sort(key=lambda item: (-item.score, item.id))
        selected = scored[:limit]
        self.search_calls.append((collection_name, int(limit), [int(item.id) for item in selected]))
        return selected

    def retrieve(self, collection_name, ids, with_vectors=True, with_payload=False):
        collection = self.collections.get(collection_name, {})
        return [collection[int(node_id)] for node_id in ids if int(node_id) in collection]

    def scroll(self, collection_name, offset=None, limit=256, with_vectors=False, with_payload=False):
        ids = sorted(self.collections.get(collection_name, {}))
        start = 0
        if offset is not None and offset in ids:
            start = ids.index(offset) + 1
        selected = ids[start : start + limit]
        next_offset = selected[-1] if start + limit < len(ids) and selected else None
        return [self.collections[collection_name][node_id] for node_id in selected], next_offset


def test_storage_round_trip(tmp_path):
    chunks = [
        Chunk(
            "蒸汽功能",
            "蒸汽",
            ("操作", "蒸汽"),
            2,
            1,
            "x.md",
            metadata={"manual_id": "manual-x", "title": "Manual X", "product_category": "coffee", "tags": ["steam"]},
        )
    ]
    vectors = np.array([[1.0, 0.0]], dtype=np.float32)
    graph = build_graph(chunks, vectors)
    JsonGraphStore(tmp_path / "graph.json").save(graph)
    loaded_graph = JsonGraphStore(tmp_path / "graph.json").load()
    assert loaded_graph.nodes[0]["text"] == "蒸汽功能"
    assert loaded_graph.nodes[0]["manual_id"] == "manual-x"
    assert loaded_graph.nodes[0]["metadata"]["tags"] == ["steam"]
    NpzVectorStore(tmp_path / "vectors.npz").add(np.array([0]), vectors)
    _, loaded_vectors = NpzVectorStore(tmp_path / "vectors.npz").load()
    np.testing.assert_array_equal(vectors, loaded_vectors)
    anchor = Anchor(anchor_key=graph.nodes[0]["anchor_key"], label="测试", node_id=0)
    JsonAnchorStore(tmp_path / "anchors.json").save([anchor])
    assert JsonAnchorStore(tmp_path / "anchors.json").load()[0].anchor_key == anchor.anchor_key


def test_graph_storage_round_trip_preserves_lineage_metadata(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    path = docs / "manual.md"
    path.write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    chunks = parse_document(path, min_chars=1, root_dir=docs, metadata={"manual_id": "coffee-manual"})
    graph = build_graph(chunks, np.array([[1.0, 0.0]], dtype=np.float32))

    JsonGraphStore(tmp_path / "graph.json").save(graph)
    loaded_graph = JsonGraphStore(tmp_path / "graph.json").load()
    metadata = loaded_graph.nodes[0]["metadata"]

    assert metadata["doc_id"] == "coffee-manual"
    assert metadata["section_path"] == ["操作"]
    assert metadata["asset_refs"] == []
    assert metadata["parser_profile"] == "markdown"
    assert metadata["parser_version"] == "1"
    assert metadata["chunk_id"].startswith("chunk:sha256:")
    assert metadata["element_ids"][0].startswith("element:sha256:")


def test_atomic_write_preserves_original_on_failure(tmp_path):
    target = tmp_path / "data.json"
    target.write_text("old", encoding="utf-8")

    def bad_write(tmp_path):
        tmp_path.write_text("new", encoding="utf-8")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        atomic_write(target, bad_write)
    assert target.read_text(encoding="utf-8") == "old"


def test_vector_search_returns_dot_product_top_k(tmp_path):
    store = NpzVectorStore(tmp_path / "vectors.npz")
    vectors = np.array([[1.0, 0.0], [0.0, 1.0], [0.8, 0.2]], dtype=np.float32)
    store.add(np.array([10, 20, 30]), vectors)
    assert store.search(np.array([1.0, 0.0], dtype=np.float32), 2) == [(10, 1.0), (30, pytest.approx(0.8))]


def test_qdrant_vector_store_round_trip_and_search():
    FakeQdrantClient.reset()
    store = QdrantVectorStore(
        kb_name="default",
        dim=2,
        url="http://qdrant:6333",
        collection_prefix="tmr",
        client_factory=FakeQdrantClient,
    )
    vectors = np.array([[1.0, 0.0], [0.0, 1.0], [0.8, 0.2]], dtype=np.float32)

    store.add(np.array([10, 20, 30]), vectors)
    ids, loaded = store.load([30, 10])

    assert ids.tolist() == [30, 10]
    np.testing.assert_array_equal(loaded, np.array([[0.8, 0.2], [1.0, 0.0]], dtype=np.float32))
    assert store.get(20).tolist() == [0.0, 1.0]
    assert store.search(np.array([1.0, 0.0], dtype=np.float32), 2) == [(10, 1.0), (30, pytest.approx(0.8))]
    assert collection_name("tmr", "product/a") == "tmr_product-a"
    assert collection_name("tmr", "product/a", generation=1) == "tmr_product-a_g1"
    assert collection_name("tmr", "product/a", generation=42) == "tmr_product-a_g42"
    with pytest.raises(ValueError):
        collection_name("tmr", "product/a", generation=0)


def test_qdrant_vector_store_update_payload_and_delete():
    FakeQdrantClient.reset()
    store = QdrantVectorStore(
        kb_name="default",
        dim=2,
        url="http://qdrant:6333",
        collection_prefix="tmr",
        client_factory=FakeQdrantClient,
    )

    store.update(
        np.array([1]),
        np.array([[1.0, 0.0]], dtype=np.float32),
        payloads=[
            {
                "build_id": "b1",
                "doc_id": "doc-1",
                "chunk_id": "chunk:sha256:abc",
                "chunk_identity_key": "sha256:key",
                "manual_id": "m1",
                "source_file": "manual.md",
                "text_hash": "sha256:text",
                "text": "must-not-be-stored",
            }
        ],
    )
    payload = FakeQdrantClient.collections["tmr_default"][1].payload

    assert payload == {
        "kb_name": "default",
        "node_id": 1,
        "build_id": "b1",
        "doc_id": "doc-1",
        "chunk_id": "chunk:sha256:abc",
        "chunk_identity_key": "sha256:key",
        "manual_id": "m1",
        "source_file": "manual.md",
        "text_hash": "sha256:text",
    }
    store.delete([1])
    assert 1 not in FakeQdrantClient.collections["tmr_default"]


def test_qdrant_vector_store_update_payloads_batches_distinct_payloads():
    FakeQdrantClient.reset()
    store = QdrantVectorStore(
        kb_name="default",
        dim=2,
        url="http://qdrant:6333",
        collection_prefix="tmr",
        client_factory=FakeQdrantClient,
    )
    store.add(np.array([1, 2]), np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))

    store.update_payloads(
        [1, 2],
        [
            {"build_id": "b2", "node_id": 1, "chunk_identity_key": "key-1", "text": "must-not-be-stored"},
            {"build_id": "b2", "node_id": 2, "chunk_identity_key": "key-2", "secret": "must-not-be-stored"},
        ],
    )

    assert FakeQdrantClient.set_payload_calls == []
    assert FakeQdrantClient.batch_payload_calls == [
        (
            "tmr_default",
            [
                (1, {"build_id": "b2", "node_id": 1, "chunk_identity_key": "key-1"}),
                (2, {"build_id": "b2", "node_id": 2, "chunk_identity_key": "key-2"}),
            ],
        )
    ]
    assert FakeQdrantClient.collections["tmr_default"][1].payload["chunk_identity_key"] == "key-1"
    assert FakeQdrantClient.collections["tmr_default"][2].payload["chunk_identity_key"] == "key-2"
    assert "text" not in FakeQdrantClient.collections["tmr_default"][1].payload
    assert "secret" not in FakeQdrantClient.collections["tmr_default"][2].payload


def test_qdrant_vector_store_update_payloads_falls_back_without_batch_support():
    class PerPointQdrantClient(FakeQdrantClient):
        batch_update_points = None

    PerPointQdrantClient.reset()
    store = QdrantVectorStore(
        kb_name="default",
        dim=2,
        url="http://qdrant:6333",
        collection_prefix="tmr",
        client_factory=PerPointQdrantClient,
    )
    store.add(np.array([1, 2]), np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))

    store.update_payloads([1, 2], [{"build_id": "b2", "node_id": 1}, {"build_id": "b2", "node_id": 2}])

    assert PerPointQdrantClient.batch_payload_calls == []
    assert PerPointQdrantClient.set_payload_calls == [
        ("tmr_default", [1], {"build_id": "b2", "node_id": 1}),
        ("tmr_default", [2], {"build_id": "b2", "node_id": 2}),
    ]


def test_qdrant_vector_store_search_candidates():
    FakeQdrantClient.reset()
    store = QdrantVectorStore(
        kb_name="default",
        dim=2,
        url="http://qdrant:6333",
        collection_prefix="tmr",
        client_factory=FakeQdrantClient,
    )
    store.add(np.array([10, 20, 30]), np.array([[1.0, 0.0], [0.0, 1.0], [0.8, 0.2]], dtype=np.float32))

    candidates = store.search_candidates(np.array([1.0, 0.0], dtype=np.float32), 2)

    assert candidates == [(10, 1.0), (30, pytest.approx(0.8))]


def test_qdrant_inspect_reports_collection_counts_and_payload_keys(monkeypatch, tmp_path, fake_embedder):
    FakeQdrantClient.reset()
    monkeypatch.setattr("tagmemorag.storage.qdrant_vector.QdrantVectorStore._create_client", lambda *args, **kwargs: FakeQdrantClient())
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        vector_store=VectorStoreConfig(provider="qdrant", collection_prefix="test"),
        model={"dim": 64},
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    save_kb(state, cfg)

    report = inspect_qdrant("default", cfg, client_factory=FakeQdrantClient)

    assert report["provider"] == "qdrant"
    assert report["configured"] is True
    assert report["collection_name"] == "test_default"
    assert report["collection_exists"] is True
    assert report["graph_loaded"] is True
    assert report["graph_node_count"] == 2
    assert report["qdrant_point_count"] == 2
    assert report["missing_vector_count"] == 0
    assert report["sample_payload_keys"] == [
        "build_id",
        "chunk_id",
        "chunk_identity_key",
        "doc_id",
        "kb_name",
        "manual_id",
        "node_id",
        "source_file",
        "text_hash",
    ]
    assert report["payload_key_coverage"]["node_id"] == 2


def test_qdrant_inspect_detects_missing_graph_vectors(monkeypatch, tmp_path, fake_embedder):
    FakeQdrantClient.reset()
    monkeypatch.setattr("tagmemorag.storage.qdrant_vector.QdrantVectorStore._create_client", lambda *args, **kwargs: FakeQdrantClient())
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        vector_store=VectorStoreConfig(provider="qdrant", collection_prefix="test"),
        model={"dim": 64},
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    save_kb(state, cfg)
    FakeQdrantClient.collections["test_default"].pop(1)

    report = inspect_qdrant("default", cfg, client_factory=FakeQdrantClient)

    assert report["graph_node_count"] == 2
    assert report["qdrant_point_count"] == 1
    assert report["missing_vector_count"] == 1
    assert report["missing_vector_sample"] == [1]
    assert "retry_incremental_rebuild_or_force_full_rebuild" in report["recommendations"]


def test_qdrant_inspect_reports_payload_keys_without_values(monkeypatch, tmp_path, fake_embedder):
    FakeQdrantClient.reset()
    monkeypatch.setattr("tagmemorag.storage.qdrant_vector.QdrantVectorStore._create_client", lambda *args, **kwargs: FakeQdrantClient())
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        vector_store=VectorStoreConfig(provider="qdrant", collection_prefix="test"),
        model={"dim": 64},
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    save_kb(state, cfg)
    FakeQdrantClient.collections["test_default"][0].payload.update({"unsafe": "secret-value", "text": "raw text"})

    report = inspect_qdrant("default", cfg, client_factory=FakeQdrantClient)
    serialized = json.dumps(report, ensure_ascii=False)

    assert "unsafe" not in report["sample_payload_keys"]
    assert "text" not in report["sample_payload_keys"]
    assert "secret-value" not in serialized
    assert "raw text" not in serialized


def test_qdrant_inspect_non_qdrant_provider_is_clear(tmp_path):
    cfg = Settings(storage=StorageConfig(data_dir=str(tmp_path / "data")), vector_store=VectorStoreConfig(provider="npz"))

    report = inspect_qdrant("default", cfg, client_factory=FakeQdrantClient)

    assert report["provider"] == "npz"
    assert report["configured"] is False
    assert report["collection_name"] == "tagmemorag_default"
    assert report["collection_exists"] is False
    assert "set_vector_store_provider_to_qdrant" in report["recommendations"]


def test_anchor_reconcile_exact_fallback_and_unresolved(tmp_path, fake_embedder):
    old_chunks = [
        Chunk("蒸汽功能用于制作奶泡", "蒸汽功能", ("操作", "蒸汽功能"), 2, 1, "x.md"),
        Chunk("紧急停机需要立即断电", "紧急停机", ("安全", "紧急停机"), 2, 2, "x.md"),
    ]
    old_vecs = fake_embedder.encode_batch([chunk.text for chunk in old_chunks])
    old_graph = build_graph(old_chunks, old_vecs)
    exact = Anchor(old_graph.nodes[0]["anchor_key"], "exact", node_id=0, old_text=old_graph.nodes[0]["text"])
    fallback = Anchor("missing-key", "fallback", node_id=1, old_text=old_graph.nodes[1]["text"])
    unresolved = Anchor("gone", "unresolved", node_id=1, old_text="完全不存在的特殊内容")

    new_chunks = [
        old_chunks[0],
        Chunk("紧急停机需要立即断电并联系售后", "紧急停机", ("安全", "紧急停机"), 2, 2, "x.md"),
    ]
    new_vecs = fake_embedder.encode_batch([chunk.text for chunk in new_chunks])
    new_graph = build_graph(new_chunks, new_vecs)
    remapped, missing = JsonAnchorStore(tmp_path / "anchors.json").reconcile(
        [exact, fallback, unresolved],
        new_graph,
        new_vecs,
        fake_embedder,
        similarity_threshold=0.5,
    )
    assert {anchor.label for anchor in remapped} == {"exact", "fallback"}
    assert [anchor.label for anchor in missing] == ["unresolved"]


def test_build_save_load_kb(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    (docs / "manual.metadata.json").write_text(
        json.dumps(
            {
                "manual_id": "coffee-manual",
                "title": "Coffee Manual",
                "source_file": "manual.md",
                "product_category": "coffee",
                "language": "zh-CN",
                "tags": ["Steam"],
            }
        ),
        encoding="utf-8",
    )
    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    save_kb(state, test_config)
    loaded = load_kb("default", test_config)
    assert loaded.graph.number_of_nodes() == state.graph.number_of_nodes()
    assert loaded.vectors.shape == state.vectors.shape
    assert loaded.graph.nodes[0]["manual_id"] == "coffee-manual"
    assert loaded.graph.nodes[0]["metadata"]["public_tags"] == ["steam"]
    assert loaded.graph.nodes[0]["metadata"]["tags"] == [
        "steam",
        "doc:coffee-manual",
        "manual:coffee-manual",
        "category:coffee",
    ]
    meta = json.loads((tmp_path / "data" / "default" / "meta.json").read_text())
    assert meta["schema_version"] == "1"


def test_build_save_load_kb_with_qdrant_vectors(monkeypatch, tmp_path, fake_embedder):
    FakeQdrantClient.reset()
    monkeypatch.setattr("tagmemorag.storage.qdrant_vector.QdrantVectorStore._create_client", lambda *args, **kwargs: FakeQdrantClient())
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        vector_store=VectorStoreConfig(provider="qdrant", collection_prefix="test"),
        model={"dim": 64},
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")

    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    save_kb(state, cfg)
    loaded = load_kb("default", cfg)

    assert not (tmp_path / "data" / "default" / "vectors.npz").exists()
    assert "test_default" in FakeQdrantClient.collections
    assert loaded.vectors.shape == state.vectors.shape
    np.testing.assert_array_equal(loaded.vectors, state.vectors)


def test_build_kb_includes_pdf_documents(monkeypatch, tmp_path, test_config, fake_embedder):
    class FakePdfPage:
        def extract_text(self):
            return "冷藏室温度设置与冰箱噪音排查。"

    class FakePdfReader:
        def __init__(self, _path: str):
            self.pages = [FakePdfPage()]

    monkeypatch.setattr("tagmemorag.parser.PdfReader", FakePdfReader)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "fridge.pdf").write_bytes(b"%PDF fake")

    state = build_kb(docs, "default", test_config, embedder=fake_embedder)

    assert state.graph.number_of_nodes() == 1
    node = state.graph.nodes[0]
    assert node["source_file"] == "fridge.pdf"
    assert node["manual_id"] == "fridge"
    assert node["product_category"] == "unknown"
    assert node["header"] == "Page 1"
    assert node["metadata"]["page_start"] == 1
    assert node["metadata"]["pdf_header_source"] == "page_fallback"
    assert node["metadata"]["pdf_parser_profile"] == "product_manual"
    assert node["metadata"]["parser_profile"] == "pdf:product_manual"
    assert node["metadata"]["doc_id"] == "fridge"
    assert node["metadata"]["chunk_id"].startswith("chunk:sha256:")
    assert "冷藏室温度" in node["text"]


def test_build_kb_includes_ocr_text_for_empty_pdf_pages(monkeypatch, tmp_path, fake_embedder):
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
            return OCRPageResult("OCR steam wand instructions.")

    monkeypatch.setattr("tagmemorag.parser.PdfReader", FakePdfReader)
    monkeypatch.setattr("tagmemorag.state.create_ocr_provider", lambda _cfg: FakeOCRProvider())
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "coffee.pdf").write_bytes(b"%PDF fake")

    state = build_kb(docs, "default", cfg, embedder=fake_embedder)

    assert state.graph.number_of_nodes() == 1
    node = state.graph.nodes[0]
    assert "OCR steam wand" in node["text"]
    assert node["metadata"]["parser_profile"] == "pdf_ocr:product_manual"
    assert node["metadata"]["ocr_provider"] == "fixture"
    assert node["metadata"]["ocr_version"] == "fixture.v1"
    assert state.meta["ocr"]["attempted"] == 1
    assert state.meta["ocr"]["created"] == 1
    assert "OCR steam wand" not in str(state.meta["ocr"])


def test_rebuild_keeps_old_state_until_done(tmp_path, test_config, fake_embedder):
    docs1 = tmp_path / "docs1"
    docs1.mkdir()
    (docs1 / "manual.md").write_text("# 旧版\n旧图内容。\n", encoding="utf-8")
    docs2 = tmp_path / "docs2"
    docs2.mkdir()
    (docs2 / "manual.md").write_text("# 新版\n新图内容。\n", encoding="utf-8")
    app = AppState(build_kb(docs1, "default", test_config, embedder=fake_embedder))
    old_build_id = app.current.build_id
    task = app.start_rebuild(docs2, "default", test_config, embedder=fake_embedder)
    assert app.get_current().build_id == old_build_id
    for _ in range(50):
        if task.status != "running":
            break
        time.sleep(0.02)
    assert task.status == "done"
    assert app.get_current().build_id != old_build_id


def test_concurrent_rebuild_is_rejected_and_search_reads_old_state(tmp_path, test_config, fake_embedder):
    class BlockingEmbedder:
        model_name = "blocking"

        def __init__(self, inner):
            self.inner = inner
            self.started = threading.Event()
            self.release = threading.Event()

        def encode_batch(self, texts):
            self.started.set()
            self.release.wait(timeout=2)
            return self.inner.encode_batch(texts)

        def encode_query(self, text):
            return self.inner.encode_query(text)

    docs1 = tmp_path / "docs1"
    docs1.mkdir()
    (docs1 / "manual.md").write_text("# 旧版\n旧图内容。\n", encoding="utf-8")
    docs2 = tmp_path / "docs2"
    docs2.mkdir()
    (docs2 / "manual.md").write_text("# 新版\n新图内容。\n", encoding="utf-8")
    app = AppState(build_kb(docs1, "default", test_config, embedder=fake_embedder))
    old_build_id = app.get_current().build_id
    blocker = BlockingEmbedder(fake_embedder)
    task = app.start_rebuild(docs2, "default", test_config, embedder=blocker)
    assert blocker.started.wait(timeout=1)
    assert app.get_current().build_id == old_build_id
    with pytest.raises(RebuildInProgressError):
        app.start_rebuild(docs2, "default", test_config, embedder=fake_embedder)
    blocker.release.set()
    for _ in range(50):
        if task.status != "running":
            break
        time.sleep(0.02)
    assert task.status == "done"
