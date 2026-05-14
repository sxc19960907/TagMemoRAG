from __future__ import annotations

import os
from pathlib import Path

import pytest

from tagmemorag.config import Settings, StorageConfig, VectorStoreConfig
from tagmemorag.embedder import HashingEmbedder
from tagmemorag.qdrant_ops import inspect_qdrant
from tagmemorag.search_runtime import execute_search, search_debug_payload
from tagmemorag.state import build_kb, load_kb, save_kb
from tagmemorag.storage.qdrant_vector import QdrantVectorStore, collection_name


QDRANT_URL = os.environ.get("TAGMEMORAG_LIVE_QDRANT_URL", "http://localhost:6333")
RUN_LIVE_QDRANT = os.environ.get("TAGMEMORAG_RUN_LIVE_QDRANT") == "1"


pytestmark = pytest.mark.skipif(
    not RUN_LIVE_QDRANT,
    reason="set TAGMEMORAG_RUN_LIVE_QDRANT=1 to run live Qdrant product-manual integration tests",
)


def test_live_qdrant_builds_and_searches_real_product_manuals(tmp_path):
    docs = Path("product_manuals")
    pdfs = sorted(docs.glob("*.pdf"))
    if len(pdfs) < 5:
        pytest.skip("real product manuals are not present")

    kb_name = "live-product-manuals"
    collection_prefix = f"tmr_live_{tmp_path.name.replace('-', '_')}"
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        vector_store=VectorStoreConfig(
            provider="qdrant",
            qdrant_url=QDRANT_URL,
            collection_prefix=collection_prefix,
            timeout_seconds=5,
        ),
        model={"provider": "hashing", "name": "hashing", "dim": 64},
        search={"ann_preselect_enabled": True, "ann_candidate_k": 32},
    )
    collection = collection_name(collection_prefix, kb_name)
    store = QdrantVectorStore(
        kb_name=kb_name,
        dim=64,
        url=QDRANT_URL,
        collection_prefix=collection_prefix,
        timeout_seconds=5,
    )
    _delete_collection_if_exists(store.client, collection)

    try:
        embedder = HashingEmbedder(dim=64)
        state = build_kb(docs, kb_name, cfg, embedder=embedder)
        assert state.graph.number_of_nodes() >= len(pdfs)

        save_kb(state, cfg)
        loaded = load_kb(kb_name, cfg)

        assert not (tmp_path / "data" / kb_name / "vectors.npz").exists()
        assert loaded.vectors.shape == state.vectors.shape

        report = inspect_qdrant(kb_name, cfg)
        assert report["collection_exists"] is True
        assert report["graph_loaded"] is True
        assert report["graph_node_count"] == state.graph.number_of_nodes()
        assert report["qdrant_point_count"] == state.graph.number_of_nodes()
        assert report["missing_vector_count"] == 0
        assert set(report["sample_payload_keys"]) >= {
            "build_id",
            "chunk_identity_key",
            "kb_name",
            "manual_id",
            "node_id",
            "source_file",
            "text_hash",
        }

        _assert_business_query(
            loaded,
            cfg,
            embedder,
            query="refrigerator display controls troubleshooting",
            expected_source="HISENSE HR6FDFF701SW.pdf",
        )
        _assert_business_query(
            loaded,
            cfg,
            embedder,
            query="oven steam clean maintenance cooking system",
            expected_source="HISENSE BSA5221.pdf",
        )
        _assert_business_query(
            loaded,
            cfg,
            embedder,
            query="清潔過濾器 排水馬達 洗衣機",
            expected_source="ASKO W6564.pdf",
        )
    finally:
        _delete_collection_if_exists(store.client, collection)


def _assert_business_query(state, cfg, embedder, *, query: str, expected_source: str) -> None:
    execution = execute_search(
        state=state,
        query_vec=embedder.encode_query(query),
        settings=cfg,
        top_k=8,
        source_k=5,
        steps=3,
        decay=0.7,
        amplitude_cutoff=0.01,
        aggregate="max",
        filters=None,
    )

    debug = search_debug_payload(
        execution,
        {"source_k": 5, "steps": 3, "aggregate": "max"},
        ann_enabled=True,
    )
    assert debug["search_strategy"] == "ann_preselect_then_wave"
    assert debug["ann_candidate_count"] > 0
    assert execution.results
    assert any(result.source_file == expected_source for result in execution.results), [
        {"source_file": result.source_file, "header": result.header, "score": result.score}
        for result in execution.results
    ]


def _delete_collection_if_exists(client, collection: str) -> None:
    try:
        exists = client.collection_exists(collection)
    except Exception:
        exists = False
    if exists:
        client.delete_collection(collection)
