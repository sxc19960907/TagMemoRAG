from __future__ import annotations

from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.auth.config_store import ConfigAuthStore
from tagmemorag.config import ApiKeyConfig, AuthConfig, CacheConfig, ObservabilityConfig, RateLimitConfig, Settings, StorageConfig
from tagmemorag.observability.metrics import reset_metrics_for_tests
from tagmemorag.state import AppState, build_kb


def _search_client(tmp_path, fake_embedder, cfg: Settings | None = None) -> TestClient:
    cfg = cfg or Settings(storage=StorageConfig(data_dir=str(tmp_path / "data")), model={"dim": 64})
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n# 清洗\n喷嘴堵塞需要清洗。\n", encoding="utf-8")
    state = build_kb(docs, "default", cfg, embedder=fake_embedder)
    api.settings = cfg
    api.embedder = fake_embedder
    api.app_state = AppState(state)
    reset_metrics_for_tests()
    return TestClient(api.app)


def test_metrics_endpoint_exposes_custom_metrics(tmp_path, fake_embedder):
    client = _search_client(tmp_path, fake_embedder)

    search = client.post("/search", json={"question": "蒸汽", "top_k": 1})
    response = client.get("/metrics")

    assert search.status_code == 200
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "tagmemorag_http_requests_total" in response.text
    assert "tagmemorag_search_requests_total" in response.text
    assert 'route="/search"' in response.text
    assert "/metrics" not in response.text


def test_metrics_endpoint_uses_configured_path(tmp_path, fake_embedder):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
        observability=ObservabilityConfig(metrics={"enabled": True, "path": "/custom-metrics"}),
    )
    client = _search_client(tmp_path, fake_embedder, cfg)

    custom = client.get("/custom-metrics")
    default = client.get("/metrics")

    assert custom.status_code == 200
    assert "tagmemorag_http_requests_total" in custom.text
    assert default.status_code == 404


def test_metrics_endpoint_is_public_when_auth_enabled(tmp_path, fake_embedder):
    secret = "tmr_live_ops"
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
        auth=AuthConfig(
            enabled=True,
            keys=[
                ApiKeyConfig(
                    id="ops",
                    hash=ConfigAuthStore.hash_plaintext(secret),
                    scopes=["search"],
                )
            ],
        ),
    )
    client = _search_client(tmp_path, fake_embedder, cfg)

    response = client.get("/metrics")

    assert response.status_code == 200


def test_metrics_can_be_disabled(tmp_path, fake_embedder):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
        observability=ObservabilityConfig(metrics={"enabled": False}),
    )
    client = _search_client(tmp_path, fake_embedder, cfg)

    response = client.get("/metrics")

    assert response.status_code == 404


def test_search_cache_hit_and_miss_metrics(tmp_path, fake_embedder):
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
        cache=CacheConfig(enabled=True, max_entries=100, ttl_seconds=3600),
    )
    client = _search_client(tmp_path, fake_embedder, cfg)
    from tagmemorag.cache.lru_ttl import LRUTTLCache

    api.app_state.query_cache = LRUTTLCache(max_entries=100, ttl_seconds=3600, now_fn=lambda: 1000.0)

    first = client.post("/search", json={"question": "蒸汽", "top_k": 1})
    second = client.post("/search", json={"question": "蒸汽", "top_k": 1})
    metrics = client.get("/metrics").text

    assert first.json()["cache"] == "miss"
    assert second.json()["cache"] == "hit"
    assert 'cache_status="miss",error_code="none",kb_name="default",outcome="success"' in metrics
    assert 'cache_status="hit",error_code="none",kb_name="default",outcome="success"' in metrics
    assert 'operation="get",outcome="miss"' in metrics
    assert 'operation="get",outcome="hit"' in metrics


def test_rate_limit_metrics_records_limited(tmp_path, fake_embedder):
    secret = "tmr_live_limited"
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
        auth=AuthConfig(
            enabled=True,
            keys=[
                ApiKeyConfig(
                    id="limited",
                    hash=ConfigAuthStore.hash_plaintext(secret),
                    scopes=["search"],
                    rate_limit_per_minute=0,
                )
            ],
        ),
        rate_limit=RateLimitConfig(enabled=True, default_per_minute=0, window_seconds=60),
    )
    client = _search_client(tmp_path, fake_embedder, cfg)
    from tagmemorag.rate_limit.memory_sliding import InMemorySlidingWindowStore

    api.app_state.auth_store = ConfigAuthStore.from_config(cfg.auth)
    api.app_state.rate_limiter = InMemorySlidingWindowStore(cfg.rate_limit.window_seconds, now_fn=lambda: 1000.0)

    response = client.get("/kb", headers={"Authorization": f"Bearer {secret}"})
    metrics = client.get("/metrics").text

    assert response.status_code == 429
    assert 'tagmemorag_rate_limit_checks_total{outcome="limited"} 1.0' in metrics
    assert 'route="/kb",status_code="429"' in metrics
    assert 'tagmemorag_http_errors_total{error_code="RATE_LIMITED",route="/kb",status_code="429"} 1.0' in metrics
