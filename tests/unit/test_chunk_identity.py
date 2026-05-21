"""Tests locking the embedder-free invariant of chunk_id (Architecture v2 § A1)."""

from __future__ import annotations

from tagmemorag.chunk_identity import parser_signature
from tagmemorag.config import ModelConfig, ParserConfig, Settings


def _settings_with_model(name: str, version: str) -> Settings:
    cfg = Settings()
    cfg.model = ModelConfig(name=name, embedding_model_version=version)
    cfg.parser = ParserConfig()
    return cfg


def test_parser_signature_does_not_depend_on_embedder_model():
    cfg_a = _settings_with_model("bge-m3", "v1")
    cfg_b = _settings_with_model("qwen3-embedding-8b", "v1.5")
    assert parser_signature(cfg_a) == parser_signature(cfg_b)


def test_parser_signature_changes_with_parser_config():
    cfg = Settings()
    cfg.parser = ParserConfig(max_chars=400)
    base = parser_signature(cfg)
    cfg.parser = ParserConfig(max_chars=800)
    changed = parser_signature(cfg)
    assert base != changed


def test_parser_signature_changes_with_parser_provider():
    cfg = Settings()
    cfg.parser = ParserConfig(provider="native")
    base = parser_signature(cfg)
    cfg.parser = ParserConfig(provider="langchain")
    changed = parser_signature(cfg)
    assert base != changed
