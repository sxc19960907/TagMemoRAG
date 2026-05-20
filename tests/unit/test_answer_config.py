from __future__ import annotations

from pathlib import Path

from tagmemorag.config import Settings, load_config


def test_answer_config_defaults():
    cfg = Settings()

    assert cfg.answer.enabled is False
    assert cfg.answer.provider == "noop"
    assert cfg.answer.prompt_version == "answer_prompt.v1"
    assert cfg.answer.api_key_env == "OPENAI_API_KEY"


def test_answer_config_yaml_override(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
answer:
  enabled: true
  provider: openai_compatible
  model_id: gpt-test
  api_key_env: ANSWER_KEY
  max_output_tokens: 123
""",
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.answer.enabled is True
    assert cfg.answer.provider == "openai_compatible"
    assert cfg.answer.model_id == "gpt-test"
    assert cfg.answer.api_key_env == "ANSWER_KEY"
    assert cfg.answer.max_output_tokens == 123
