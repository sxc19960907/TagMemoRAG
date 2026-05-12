from __future__ import annotations

from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.auth.config_store import ConfigAuthStore
from tagmemorag.cache.lru_ttl import LRUTTLCache
from tagmemorag.config import ApiKeyConfig, AuthConfig, CacheConfig, RateLimitConfig, Settings, StorageConfig
from tagmemorag.rate_limit.memory_sliding import InMemorySlidingWindowStore
from tagmemorag.state import AppState, build_kb


def _settings(tmp_path, *, rate: int = 100) -> Settings:
    cs_secret = "tmr_live_cs"
    admin_secret = "tmr_live_admin"
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
        auth=AuthConfig(
            enabled=True,
            keys=[
                ApiKeyConfig(
                    id="cs-a",
                    hash=ConfigAuthStore.hash_plaintext(cs_secret),
                    kb_allowlist=["kb-a"],
                    scopes=["search"],
                    rate_limit_per_minute=rate,
                ),
                ApiKeyConfig(
                    id="admin",
                    hash=ConfigAuthStore.hash_plaintext(admin_secret),
                    kb_allowlist=[],
                    scopes=["admin"],
                    rate_limit_per_minute=1000,
                ),
            ],
        ),
        rate_limit=RateLimitConfig(enabled=True, default_per_minute=rate, window_seconds=60),
        cache=CacheConfig(enabled=True, max_entries=100, ttl_seconds=3600),
    )


def _client(tmp_path, fake_embedder, *, rate: int = 100) -> TestClient:
    cfg = _settings(tmp_path, rate=rate)
    docs_a = tmp_path / "docs-a"
    docs_b = tmp_path / "docs-b"
    docs_a.mkdir()
    docs_b.mkdir()
    (docs_a / "manual.md").write_text("# A\n蒸汽功能可以打奶泡。\n# A2\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    (docs_b / "manual.md").write_text("# B\n保养需要断电。\n", encoding="utf-8")
    state_a = build_kb(docs_a, "kb-a", cfg, embedder=fake_embedder)
    state_b = build_kb(docs_b, "kb-b", cfg, embedder=fake_embedder)
    app_state = AppState()
    app_state.swap_kb("kb-a", state_a)
    app_state.swap_kb("kb-b", state_b)
    app_state.auth_store = ConfigAuthStore.from_config(cfg.auth)
    app_state.rate_limiter = InMemorySlidingWindowStore(cfg.rate_limit.window_seconds, now_fn=lambda: 1000.0)
    app_state.query_cache = LRUTTLCache(cfg.cache.max_entries, cfg.cache.ttl_seconds, now_fn=lambda: 1000.0)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = app_state
    return TestClient(api.app)


def test_m2_auth_scope_kb_cache_and_list(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder)

    assert client.post("/search", json={"question": "蒸汽", "kb_name": "kb-a"}).status_code == 401
    assert client.post("/search", headers={"Authorization": "Bearer bad"}, json={"question": "蒸汽", "kb_name": "kb-a"}).status_code == 401

    cs_headers = {"Authorization": "Bearer tmr_live_cs"}
    first = client.post("/search", headers=cs_headers, json={"question": "蒸汽", "kb_name": "kb-a"})
    assert first.status_code == 200
    assert first.json()["cache"] == "miss"
    assert first.headers["X-RateLimit-Limit"] == "100"

    second = client.post("/search", headers=cs_headers, json={"question": "  蒸汽  ", "kb_name": "kb-a"})
    assert second.status_code == 200
    assert second.json()["cache"] == "hit"

    forbidden = client.post("/search", headers=cs_headers, json={"question": "保养", "kb_name": "kb-b"})
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"

    rebuild = client.post("/rebuild", headers=cs_headers, json={"docs_dir": str(tmp_path), "kb_name": "kb-a"})
    assert rebuild.status_code == 403

    visible = client.get("/kb", headers=cs_headers).json()["kbs"]
    assert [item["kb_name"] for item in visible] == ["kb-a"]

    admin_headers = {"Authorization": "Bearer tmr_live_admin"}
    all_kbs = client.get("/kb", headers=admin_headers).json()["kbs"]
    assert {item["kb_name"] for item in all_kbs} == {"kb-a", "kb-b"}

    cleared = client.post("/admin/cache/clear", headers=admin_headers, json={"kb_name": "kb-a"})
    assert cleared.status_code == 200
    assert cleared.json()["cleared_count"] == 1


def test_m2_rate_limit_response(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder, rate=1)
    headers = {"Authorization": "Bearer tmr_live_cs"}

    assert client.get("/kb", headers=headers).status_code == 200
    response = client.get("/kb", headers=headers)

    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"
    assert "Retry-After" in response.headers


def test_m2_key_level_zero_rate_limit_denies(tmp_path, fake_embedder):
    client = _client(tmp_path, fake_embedder, rate=0)
    headers = {"Authorization": "Bearer tmr_live_cs"}

    response = client.get("/kb", headers=headers)

    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"
