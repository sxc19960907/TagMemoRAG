"""Tests for /admin/generation/* endpoints (T1 Slice 7)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.auth.config_store import ConfigAuthStore
from tagmemorag.config import (
    ApiKeyConfig,
    AuthConfig,
    Settings,
    StorageConfig,
)
from tagmemorag.indexgen import (
    INDEXGEN_META_SCHEMA_VERSION,
    KbMeta,
    ReadyGeneration,
    read_meta,
)
from tagmemorag.state import AppState


def _settings(tmp_path) -> Settings:
    admin_secret = "tmr_live_admin"
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
        auth=AuthConfig(
            enabled=True,
            keys=[
                ApiKeyConfig(
                    id="admin",
                    hash=ConfigAuthStore.hash_plaintext(admin_secret),
                    kb_allowlist=[],
                    scopes=["admin"],
                    rate_limit_per_minute=1000,
                ),
            ],
        ),
    )


def _client(tmp_path, fake_embedder) -> TestClient:
    cfg = _settings(tmp_path)
    app_state = AppState()
    app_state.auth_store = ConfigAuthStore.from_config(cfg.auth)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = app_state
    return TestClient(api.app)


def _seed_index(cfg: Settings, kb_name: str) -> None:
    kb_root = Path(cfg.storage.data_dir) / kb_name
    kb_root.mkdir(parents=True, exist_ok=True)
    g1 = ReadyGeneration(
        created_at="2026-05-17T10:00:00Z",
        swap_at="2026-05-17T10:00:00Z",
        retired_at=None,
        parser_version="default",
        chunker_version="legacy",
        embedding_model_id=cfg.model.effective_embedding_model_id,
        embedding_model_version=cfg.model.embedding_model_version,
        index_schema_version=int(cfg.storage.schema_version),
        chunk_count=0,
        build_id="g1-seeded",
    )
    meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name=kb_name,
        active_generation=1,
        shadow_generation=None,
        generations={1: g1},
    )
    (kb_root / "index.json").write_text(
        json.dumps(meta.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _wait_for_status_ready(client, headers, kb_name: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/admin/generation/status?kb_name={kb_name}", headers=headers)
        assert resp.status_code == 200
        meta = resp.json()
        shadow = meta.get("shadow_generation")
        if shadow is not None:
            entry = meta["generations"].get(str(shadow))
            if entry and entry.get("status") in {"ready", "failed"}:
                return meta
        time.sleep(0.05)
    raise AssertionError(f"shadow did not become ready within {timeout}s")


def test_status_returns_full_index_meta(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    cfg = api.settings
    _seed_index(cfg, "kb-x")
    admin = {"Authorization": "Bearer tmr_live_admin"}

    resp = client.get("/admin/generation/status?kb_name=kb-x", headers=admin)
    assert resp.status_code == 200
    body = resp.json()
    assert body["active_generation"] == 1
    assert body["shadow_generation"] is None
    assert "1" in body["generations"]


def test_status_no_such_kb_returns_error(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    admin = {"Authorization": "Bearer tmr_live_admin"}

    resp = client.get("/admin/generation/status?kb_name=missing", headers=admin)
    assert resp.status_code in {400, 404, 500}
    assert resp.json()["code"] == "INDEXGEN_NO_SUCH_KB"


def test_admin_endpoints_require_admin_scope(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    _seed_index(api.settings, "kb-y")

    # No auth header
    assert client.get("/admin/generation/status?kb_name=kb-y").status_code == 401
    assert client.post("/admin/generation/build-shadow", json={"kb_name": "kb-y"}).status_code == 401
    assert client.post("/admin/generation/swap", json={"kb_name": "kb-y"}).status_code == 401
    assert client.post("/admin/generation/retire", json={"kb_name": "kb-y", "generation": 1}).status_code == 401
    assert client.post("/admin/generation/cancel-shadow", json={"kb_name": "kb-y"}).status_code == 401


def test_build_shadow_requires_version_diff(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    _seed_index(api.settings, "kb-nodiff")
    admin = {"Authorization": "Bearer tmr_live_admin"}

    resp = client.post(
        "/admin/generation/build-shadow",
        headers=admin,
        json={"kb_name": "kb-nodiff"},
    )
    assert resp.status_code in {400, 422, 500}
    assert resp.json()["code"] == "INDEXGEN_NO_VERSION_DIFF"


def test_build_shadow_then_swap_then_retire_force(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    cfg = api.settings
    _seed_index(cfg, "kb-flow")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")

    admin = {"Authorization": "Bearer tmr_live_admin"}

    # 1. build-shadow
    resp = client.post(
        "/admin/generation/build-shadow",
        headers=admin,
        json={
            "kb_name": "kb-flow",
            "docs_dir": str(docs),
            "embedding_model_version": "v2",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["shadow_generation"] == 2
    assert body["task_id"]

    # 2. wait for ready
    meta = _wait_for_status_ready(client, admin, "kb-flow")
    assert meta["generations"]["2"]["status"] == "ready"

    # 3. swap
    resp = client.post(
        "/admin/generation/swap", headers=admin, json={"kb_name": "kb-flow"}
    )
    assert resp.status_code == 200
    swap_body = resp.json()
    assert swap_body["previous_active"] == 1
    assert swap_body["new_active"] == 2

    # 4. retire g1 with force=True (within 24h window)
    resp = client.post(
        "/admin/generation/retire",
        headers=admin,
        json={"kb_name": "kb-flow", "generation": 1, "force": True},
    )
    assert resp.status_code == 200
    assert resp.json()["retired_generation"] == 1

    # 5. status reflects everything
    final = read_meta(Path(cfg.storage.data_dir) / "kb-flow")
    assert final.active_generation == 2
    assert final.shadow_generation is None
    assert final.generations[1].retired_at is not None


def test_retire_too_early_without_force(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    cfg = api.settings
    _seed_index(cfg, "kb-early")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "m.md").write_text("# T\nv\n", encoding="utf-8")

    admin = {"Authorization": "Bearer tmr_live_admin"}
    client.post(
        "/admin/generation/build-shadow",
        headers=admin,
        json={
            "kb_name": "kb-early",
            "docs_dir": str(docs),
            "embedding_model_version": "v2",
        },
    )
    _wait_for_status_ready(client, admin, "kb-early")
    client.post("/admin/generation/swap", headers=admin, json={"kb_name": "kb-early"})

    resp = client.post(
        "/admin/generation/retire",
        headers=admin,
        json={"kb_name": "kb-early", "generation": 1, "force": False},
    )
    assert resp.json()["code"] == "INDEXGEN_RETIRE_TOO_EARLY"
    assert "retry_after_seconds" in resp.json()["detail"]


def test_swap_no_shadow_returns_error(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    _seed_index(api.settings, "kb-noshadow")
    admin = {"Authorization": "Bearer tmr_live_admin"}

    resp = client.post(
        "/admin/generation/swap", headers=admin, json={"kb_name": "kb-noshadow"}
    )
    assert resp.json()["code"] == "INDEXGEN_NO_SHADOW"


def test_cancel_shadow_clears_shadow_slot(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    cfg = api.settings
    _seed_index(cfg, "kb-cancel")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "m.md").write_text("# T\nv\n", encoding="utf-8")

    admin = {"Authorization": "Bearer tmr_live_admin"}
    client.post(
        "/admin/generation/build-shadow",
        headers=admin,
        json={
            "kb_name": "kb-cancel",
            "docs_dir": str(docs),
            "embedding_model_version": "v2",
        },
    )
    _wait_for_status_ready(client, admin, "kb-cancel")

    resp = client.post(
        "/admin/generation/cancel-shadow",
        headers=admin,
        json={"kb_name": "kb-cancel"},
    )
    assert resp.status_code == 200
    assert resp.json()["cancelled_generation"] == 2

    final = read_meta(Path(cfg.storage.data_dir) / "kb-cancel")
    assert final.shadow_generation is None
    assert 2 not in final.generations
    assert not (Path(cfg.storage.data_dir) / "kb-cancel" / "g2").exists()


def test_cancel_shadow_no_shadow_returns_error(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)
    _seed_index(api.settings, "kb-nocancel")
    admin = {"Authorization": "Bearer tmr_live_admin"}

    resp = client.post(
        "/admin/generation/cancel-shadow",
        headers=admin,
        json={"kb_name": "kb-nocancel"},
    )
    assert resp.json()["code"] == "INDEXGEN_NO_SHADOW"
