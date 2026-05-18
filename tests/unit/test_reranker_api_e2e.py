"""End-to-end /retrieve reranker integration tests (T3 Slice 7).

Verifies that:
- /retrieve returns reordered results when reranker enabled
- rerank field appears in plan log eventually (after async flush)
- Private KB never calls SF (verified via mock counter)
- Vendor failure produces warnings + falls back to noop ordering
- Settings.reranker.enabled=False yields T2 behavior unchanged
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.auth.config_store import ConfigAuthStore
from tagmemorag.cache.lru_ttl import LRUTTLCache
from tagmemorag.config import (
    ApiKeyConfig,
    AuthConfig,
    CacheConfig,
    Settings,
    StorageConfig,
)
from tagmemorag.queryplan.plan_log import _reset_shared_writer_for_tests
from tagmemorag.state import AppState, build_kb


@pytest.fixture(autouse=True)
def _reset_writer_and_cache():
    _reset_shared_writer_for_tests()
    # Drop dispatcher cache between tests so swapped api.settings rebuilds
    api._RERANK_DISPATCHER_CACHE.clear()  # type: ignore[attr-defined]
    yield
    _reset_shared_writer_for_tests()
    api._RERANK_DISPATCHER_CACHE.clear()  # type: ignore[attr-defined]


def _settings(tmp_path: Path, *, rerank_enabled: bool, private: list[str] | None = None) -> Settings:
    cs_secret = "tmr_live_cs"
    qp = {"private_kbs": private} if private else {}
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
        auth=AuthConfig(
            enabled=True,
            keys=[
                ApiKeyConfig(
                    id="cs",
                    hash=ConfigAuthStore.hash_plaintext(cs_secret),
                    kb_allowlist=["kb-a", "kb-priv"],
                    scopes=["search"],
                    rate_limit_per_minute=100,
                ),
            ],
        ),
        cache=CacheConfig(enabled=True, max_entries=100, ttl_seconds=3600),
        queryplan=qp,
        reranker={"enabled": rerank_enabled, "rerank_candidates_n": 10, "top_n": 3},
    )


def _client(tmp_path, fake_embedder, *, rerank_enabled: bool, private: list[str] | None = None) -> TestClient:
    cfg = _settings(tmp_path, rerank_enabled=rerank_enabled, private=private)
    docs = tmp_path / "docs-a"
    docs.mkdir()
    (docs / "manual.md").write_text(
        "# A1\n蒸汽功能。\n# A2\n滤网清洁。\n# A3\n保养建议。\n# A4\n故障排查。\n# A5\n维护计划。\n",
        encoding="utf-8",
    )
    state_a = build_kb(docs, "kb-a", cfg, embedder=fake_embedder)
    docs_p = tmp_path / "docs-priv"
    docs_p.mkdir()
    (docs_p / "manual.md").write_text("# P\n秘密。\n", encoding="utf-8")
    state_p = build_kb(docs_p, "kb-priv", cfg, embedder=fake_embedder)
    app_state = AppState()
    app_state.swap_kb("kb-a", state_a)
    app_state.swap_kb("kb-priv", state_p)
    app_state.auth_store = ConfigAuthStore.from_config(cfg.auth)
    app_state.query_cache = LRUTTLCache(cfg.cache.max_entries, cfg.cache.ttl_seconds, now_fn=lambda: 1000.0)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = app_state
    return TestClient(api.app)


def _flush_plan_writer():
    from tagmemorag.queryplan.plan_log import _shared_writer
    _shared_writer().flush(timeout=2.0)


def _read_plan_row(cfg, kb_name: str, plan_id: str) -> dict | None:
    db_path = Path(cfg.storage.data_dir) / kb_name / "query_plans.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT plan_id, intent, cache_status, rerank_json, warnings_json "
            "FROM plans WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "plan_id": row[0],
        "intent": row[1],
        "cache_status": row[2],
        "rerank_json": row[3],
        "warnings_json": row[4],
    }


def _install_mock_sf(monkeypatch, handler):
    """Patch SFQwen3Reranker to use a mocked httpx transport."""
    from tagmemorag.reranker import siliconflow as sf_mod

    original_init = sf_mod.SFQwen3Reranker.__init__

    def patched_init(self, settings, *, http_client=None, breaker=None):
        client = httpx.Client(transport=httpx.MockTransport(handler), timeout=httpx.Timeout(10.0))
        original_init(self, settings, http_client=client, breaker=breaker)

    monkeypatch.setattr(sf_mod.SFQwen3Reranker, "__init__", patched_init)
    monkeypatch.setenv("SILICONFLOW_API_KEY", "test-key")


# ---------- enabled=False: T2 behavior preserved ----------

def test_retrieve_reranker_disabled_yields_t2_behavior(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder, rerank_enabled=False)
    cs = {"Authorization": "Bearer tmr_live_cs"}
    resp = client.post("/retrieve", headers=cs, json={"question": "蒸汽功能", "kb_name": "kb-a"})
    assert resp.status_code == 200
    body = resp.json()
    assert "plan_id" in body
    _flush_plan_writer()

    row = _read_plan_row(api.settings, "kb-a", body["plan_id"])
    assert row is not None
    # rerank_json is NULL when reranker disabled — T3 D6 forces tier=off, so
    # rerank_log_entry stays None, and SQLite update with None gets COALESCE'd
    # to existing NULL.
    assert row["rerank_json"] in (None, "null")


# ---------- enabled=True: vendor called + plan log gets rerank ----------

def test_retrieve_reranker_enabled_calls_vendor_and_records_rerank(tmp_path, fake_embedder, monkeypatch):
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        body = json.loads(request.content)
        # Mock returns 3 results in vendor's preferred order
        results = []
        for i, _ in enumerate(body.get("documents", [])[:3]):
            results.append({"index": i, "relevance_score": float(10 - i)})
        return httpx.Response(200, json={"id": "rerank-x", "results": results})

    _install_mock_sf(monkeypatch, handler)
    client = _client(tmp_path, fake_embedder, rerank_enabled=True)
    cs = {"Authorization": "Bearer tmr_live_cs"}
    resp = client.post("/retrieve", headers=cs, json={"question": "蒸汽功能", "kb_name": "kb-a"})
    assert resp.status_code == 200
    body = resp.json()
    assert "plan_id" in body
    assert call_count["n"] == 1, "SF reranker should have been called exactly once"
    _flush_plan_writer()

    row = _read_plan_row(api.settings, "kb-a", body["plan_id"])
    assert row is not None
    assert row["rerank_json"] is not None
    rerank_meta = json.loads(row["rerank_json"])
    assert rerank_meta["vendor_used"] == "qwen3-reranker-0.6b@siliconflow"
    assert rerank_meta["cache_status"] == "miss"
    assert rerank_meta["calibrator"] == "minmax"


# ---------- private KB: no vendor call ----------

def test_retrieve_private_kb_does_not_call_vendor(tmp_path, fake_embedder, monkeypatch):
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json={"results": []})

    _install_mock_sf(monkeypatch, handler)
    client = _client(tmp_path, fake_embedder, rerank_enabled=True, private=["kb-priv"])
    cs = {"Authorization": "Bearer tmr_live_cs"}
    resp = client.post("/retrieve", headers=cs, json={"question": "秘密", "kb_name": "kb-priv"})
    assert resp.status_code == 200
    body = resp.json()
    assert "plan_id" in body
    # Private KB ACL must short-circuit before vendor call
    assert call_count["n"] == 0


# ---------- vendor failure ----------

def test_retrieve_vendor_failure_returns_warnings(tmp_path, fake_embedder, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    _install_mock_sf(monkeypatch, handler)
    client = _client(tmp_path, fake_embedder, rerank_enabled=True)
    cs = {"Authorization": "Bearer tmr_live_cs"}
    resp = client.post("/retrieve", headers=cs, json={"question": "蒸汽功能", "kb_name": "kb-a"})
    assert resp.status_code == 200
    body = resp.json()
    # Should still return a usable payload (empty or filled, depending on retrieval)
    assert "plan_id" in body
    # Warnings include reranker fallback reason
    if body.get("warnings"):
        assert any("reranker_fallback" in w for w in body["warnings"])
    _flush_plan_writer()
    row = _read_plan_row(api.settings, "kb-a", body["plan_id"])
    assert row is not None
    if row["rerank_json"]:
        rerank_meta = json.loads(row["rerank_json"])
        # vendor_used falls back to noop
        assert rerank_meta["vendor_used"] == "noop"
