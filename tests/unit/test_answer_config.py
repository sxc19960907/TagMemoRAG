from __future__ import annotations

from pathlib import Path

from tagmemorag.config import Settings, load_config


def test_answer_config_defaults():
    cfg = Settings()

    assert cfg.answer.enabled is False
    assert cfg.answer.provider == "noop"
    assert cfg.answer.prompt_version == "answer_prompt.v1"
    assert cfg.answer.api_key_env == "OPENAI_API_KEY"
    assert cfg.agentic.mode == "classic"
    assert cfg.agentic.decision.enabled is False
    assert cfg.agentic.decision.provider == "noop"
    assert cfg.agentic.decision.max_output_tokens == 256
    assert cfg.agentic.decision.tool_schema_mode == "openai_tools"
    assert cfg.agentic.decision.json_strict is True


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
agentic:
  mode: agentic
  decision:
    enabled: true
    provider: openai_compatible
    model_id: decision-test
    base_url: https://decision.example/v1
    api_key_env: DECISION_KEY
    tool_schema_mode: json_object
""",
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.answer.enabled is True
    assert cfg.answer.provider == "openai_compatible"
    assert cfg.answer.model_id == "gpt-test"
    assert cfg.answer.api_key_env == "ANSWER_KEY"
    assert cfg.answer.max_output_tokens == 123
    assert cfg.agentic.mode == "agentic"
    assert cfg.agentic.decision.enabled is True
    assert cfg.agentic.decision.provider == "openai_compatible"
    assert cfg.agentic.decision.model_id == "decision-test"
    assert cfg.agentic.decision.base_url == "https://decision.example/v1"
    assert cfg.agentic.decision.api_key_env == "DECISION_KEY"
    assert cfg.agentic.decision.tool_schema_mode == "json_object"


def test_production_provider_profile_uses_deepseek_safe_answer_budget():
    cfg = load_config("examples/config/production-provider-verification.yaml")

    assert cfg.answer.provider == "openai_compatible"
    assert cfg.answer.model_id == "deepseek-v4-flash"
    assert cfg.answer.max_output_tokens == 1024
