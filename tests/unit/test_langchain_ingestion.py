from __future__ import annotations

import builtins

import pytest

from tagmemorag.config import ParserConfig, Settings, StorageConfig
from tagmemorag.parser_provider import supported_document_suffixes
from tagmemorag.state import build_kb


def test_native_provider_keeps_default_suffixes():
    assert supported_document_suffixes(ParserConfig(provider="native")) == frozenset({".md", ".pdf", ".txt"})


def test_langchain_provider_adds_html_suffixes():
    assert {".html", ".htm"}.issubset(supported_document_suffixes(ParserConfig(provider="langchain")))


def test_langchain_provider_builds_html_document(tmp_path, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.html").write_text(
        "<html><head><title>HTML Manual</title></head><body><h1>Steam Care</h1><p>Clean the steam nozzle after milk foam.</p></body></html>",
        encoding="utf-8",
    )
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        parser=ParserConfig(provider="langchain", min_chars=1),
        model={"dim": 64},
    )

    state = build_kb(docs, "default", cfg, embedder=fake_embedder)

    assert state.graph.number_of_nodes() >= 1
    node = state.graph.nodes[0]
    assert node["source_file"] == "manual.html"
    assert node["metadata"]["parser_profile"].startswith("langchain:html:")
    assert node["metadata"]["langchain_source"] == "manual.html"
    assert "Clean the steam nozzle" in node["text"]


def test_langchain_provider_missing_extra_fails_clearly(tmp_path, fake_embedder, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.html").write_text("<html><body><p>Steam care.</p></body></html>", encoding="utf-8")
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        parser=ParserConfig(provider="langchain", min_chars=1),
        model={"dim": 64},
    )
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("langchain_community"):
            raise ImportError("simulated missing langchain extra")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="optional 'langchain' extra"):
        build_kb(docs, "default", cfg, embedder=fake_embedder)
