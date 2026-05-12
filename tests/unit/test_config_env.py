from __future__ import annotations

from tagmemorag.config import load_config


def test_env_overrides_yaml(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text("server:\n  port: 8000\n", encoding="utf-8")
    monkeypatch.setenv("TAGMEMORAG__SERVER__PORT", "9000")

    assert load_config(config).server.port == 9000


def test_env_overrides_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__SERVER__PORT", "9001")

    assert load_config(tmp_path / "missing.yaml").server.port == 9001


def test_nested_env_delimiter(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__MODEL__NAME", "hashing")

    assert load_config(tmp_path / "missing.yaml").model.name == "hashing"


def test_http_model_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__MODEL__PROVIDER", "http")
    monkeypatch.setenv("TAGMEMORAG__MODEL__BASE_URL", "https://api.siliconflow.cn/v1")
    monkeypatch.setenv("TAGMEMORAG__MODEL__API_KEY_ENV", "SILICONFLOW_API_KEY")
    monkeypatch.setenv("TAGMEMORAG__MODEL__DIMENSIONS", "4096")

    cfg = load_config(tmp_path / "missing.yaml")

    assert cfg.model.provider == "http"
    assert cfg.model.base_url == "https://api.siliconflow.cn/v1"
    assert cfg.model.api_key_env == "SILICONFLOW_API_KEY"
    assert cfg.model.dimensions == 4096


def test_yaml_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("TAGMEMORAG__SERVER__PORT", raising=False)
    config = tmp_path / "config.yaml"
    config.write_text("server:\n  port: 8123\n", encoding="utf-8")

    assert load_config(config).server.port == 8123
