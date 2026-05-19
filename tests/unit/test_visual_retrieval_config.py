from __future__ import annotations

from pathlib import Path

from tagmemorag.config import Settings, load_config


def test_visual_retrieval_config_defaults():
    cfg = Settings()

    assert cfg.visual_retrieval.enabled is False
    assert cfg.visual_retrieval.provider == "deterministic"
    assert cfg.visual_retrieval.reranker == "noop"
    assert cfg.visual_retrieval.trigger == "visual_intent"
    assert cfg.visual_retrieval.max_candidates == 4


def test_visual_retrieval_config_yaml_override(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
visual_retrieval:
  enabled: true
  max_candidates: 2
  min_score: 0.25
  provider_version: fixture.v1
""",
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.visual_retrieval.enabled is True
    assert cfg.visual_retrieval.max_candidates == 2
    assert cfg.visual_retrieval.min_score == 0.25
    assert cfg.visual_retrieval.provider_version == "fixture.v1"
