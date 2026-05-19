from __future__ import annotations

from pathlib import Path

from tagmemorag.config import Settings, load_config


def test_connectors_config_defaults():
    cfg = Settings()

    assert cfg.connectors.enabled is False
    assert cfg.connectors.provider == "fixture"
    assert cfg.connectors.materialized_root_dir == "data/connectors"
    assert cfg.connectors.strict_sync is False


def test_connectors_config_yaml_override(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
connectors:
  enabled: true
  provider: fixture
  materialized_root_dir: /tmp/connector-docs
  strict_sync: true
""",
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.connectors.enabled is True
    assert cfg.connectors.materialized_root_dir == "/tmp/connector-docs"
    assert cfg.connectors.strict_sync is True
