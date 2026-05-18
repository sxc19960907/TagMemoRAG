"""API integration tests for QueryPlan plan_id in responses (T2 Slice 5).

Covers /search and /retrieve plan_id propagation, out-of-scope short-circuit,
private KB persistence opt-out, and cache hit also producing fresh plan_id.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

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
def _reset_writer():
    _reset_shared_writer_for_tests()
    yield
    _reset_shared_writer_for_tests()


def _settings(tmp_path: Path, *, private_kbs: list[str] | None = None) -> Settings:
    cs_secret = "tmr_live_cs"
    qp = {"private_kbs": private_kbs} if private_kbs else {}
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
    )


def _client(tmp_path, fake_embedder, *, private_kbs=None) -> TestClient:
    cfg = _settings(tmp_path, private_kbs=private_kbs)
    docs = tmp_path / "docs-a"
    docs.mkdir()
    (docs / "manual.md").write_text(
        "# A\n蒸汽功能可以打奶泡。\n# A2\n清洁滤网每月一次。\n",
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


def _flush_writer():
    """Block until BackgroundWriter has processed queued updates."""
    from tagmemorag.queryplan.plan_log import _shared_writer
    w = _shared_writer()
    w.flush(timeout=2.0)


def _read_plans_db(cfg, kb_name: str) -> list[dict]:
    db_path = Path(cfg.storage.data_dir) / kb_name / "query_plans.db"
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT plan_id, kb_name, intent, cache_status, served_by_build_id, "
            "evidence_ids_json, warnings_json FROM plans"
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "plan_id": r[0], "kb_name": r[1], "intent": r[2],
            "cache_status": r[3], "served_by_build_id": r[4],
            "evidence_ids_json": r[5], "warnings_json": r[6],
        }
        for r in rows
    ]


# ---------- /search ----------

def test_search_response_contains_plan_id(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    cs = {"Authorization": "Bearer tmr_live_cs"}

    resp = client.post("/search", headers=cs, json={"question": "蒸汽", "kb_name": "kb-a"})
    assert resp.status_code == 200
    body = resp.json()
    assert "plan_id" in body
    assert isinstance(body["plan_id"], str)
    assert len(body["plan_id"]) > 0


def test_search_plan_persisted_to_sqlite(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    cs = {"Authorization": "Bearer tmr_live_cs"}

    resp = client.post("/search", headers=cs, json={"question": "蒸汽", "kb_name": "kb-a"})
    plan_id = resp.json()["plan_id"]
    _flush_writer()

    rows = _read_plans_db(api.settings, "kb-a")
    matched = [r for r in rows if r["plan_id"] == plan_id]
    assert len(matched) == 1
    assert matched[0]["intent"] == "text_answer"
    assert matched[0]["cache_status"] in {"disabled", "miss"}  # cache miss path


def test_search_cache_hit_produces_fresh_plan_id(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    cs = {"Authorization": "Bearer tmr_live_cs"}

    resp1 = client.post("/search", headers=cs, json={"question": "蒸汽", "kb_name": "kb-a"})
    pid1 = resp1.json()["plan_id"]
    resp2 = client.post("/search", headers=cs, json={"question": "蒸汽", "kb_name": "kb-a"})
    pid2 = resp2.json()["plan_id"]
    assert pid1 != pid2  # fresh plan_id even on cache hit
    assert resp2.json().get("cache") == "hit"
    _flush_writer()

    rows = _read_plans_db(api.settings, "kb-a")
    cache_statuses = {r["cache_status"] for r in rows}
    # Both miss and hit should appear
    assert "hit" in cache_statuses
    assert "miss" in cache_statuses


def test_search_out_of_scope_short_circuits(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    cs = {"Authorization": "Bearer tmr_live_cs"}

    resp = client.post(
        "/search",
        headers=cs,
        json={"question": "今天天气怎么样", "kb_name": "kb-a"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == []
    assert "warnings" in body
    assert "out_of_scope_intent" in body["warnings"]
    assert "plan_id" in body
    _flush_writer()

    rows = _read_plans_db(api.settings, "kb-a")
    out_of_scope = [r for r in rows if r["intent"] == "out_of_scope"]
    assert len(out_of_scope) >= 1


def test_private_kb_does_not_persist_plan(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder, private_kbs=["kb-priv"])
    cs = {"Authorization": "Bearer tmr_live_cs"}

    resp = client.post("/search", headers=cs, json={"question": "秘密", "kb_name": "kb-priv"})
    assert resp.status_code == 200
    body = resp.json()
    # plan_id is still returned
    assert "plan_id" in body
    _flush_writer()

    # SQLite file MUST NOT exist for private KB (insert_basic skipped + writer
    # would only create the file via update — but UPDATE on non-existent row
    # may create the DB depending on connection, so we check NO MATCHING ROW.)
    rows = _read_plans_db(api.settings, "kb-priv")
    matched = [r for r in rows if r["plan_id"] == body["plan_id"]]
    assert matched == []


# ---------- /retrieve ----------

def test_retrieve_response_contains_plan_id(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    cs = {"Authorization": "Bearer tmr_live_cs"}

    resp = client.post("/retrieve", headers=cs, json={"question": "蒸汽", "kb_name": "kb-a"})
    assert resp.status_code == 200
    body = resp.json()
    assert "plan_id" in body


def test_retrieve_out_of_scope_returns_empty_payload(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    cs = {"Authorization": "Bearer tmr_live_cs"}

    resp = client.post(
        "/retrieve",
        headers=cs,
        json={"question": "今天天气如何", "kb_name": "kb-a"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == []
    assert body["evidence"] == []
    assert body.get("context_pack", {}).get("items") == []
    assert "out_of_scope_intent" in body.get("warnings", [])
    assert "plan_id" in body


# ---------- BudgetSpec wire-up ----------

def test_search_accepts_budget_spec(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    cs = {"Authorization": "Bearer tmr_live_cs"}

    resp = client.post(
        "/search",
        headers=cs,
        json={"question": "蒸汽", "kb_name": "kb-a", "budget": {"latency_ms": 8000}},
    )
    assert resp.status_code == 200
    assert "plan_id" in resp.json()
