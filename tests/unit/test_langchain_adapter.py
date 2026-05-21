from __future__ import annotations

from dataclasses import dataclass
import builtins

import pytest

from tagmemorag.langchain_adapter.compare import _stats
from tagmemorag.langchain_adapter.loader_splitter import (
    LangChainAdapterUnavailable,
    documents_to_chunks,
    parse_langchain_document,
)
from tagmemorag.types import Chunk


@dataclass
class _FakeDocument:
    page_content: str
    metadata: dict


def test_missing_langchain_extra_reports_clear_error(tmp_path, monkeypatch):
    path = tmp_path / "manual.md"
    path.write_text("# Manual\nUse clean water before brewing.", encoding="utf-8")

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("langchain_community"):
            raise ImportError("simulated missing langchain extra")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(LangChainAdapterUnavailable, match="optional 'langchain' extra"):
        parse_langchain_document(path)


def test_documents_to_chunks_preserves_metadata_and_lineage(tmp_path):
    path = tmp_path / "manual.md"
    docs = [
        _FakeDocument(
            page_content="Use clean water before brewing.",
            metadata={"source": "/tmp/private/manual.md", "page": 0, "title": "Setup"},
        )
    ]

    chunks = documents_to_chunks(
        docs,
        source_path=path,
        root_dir=tmp_path,
        metadata={"manual_id": "coffee", "tags": ["setup"]},
        parser_profile="langchain:md:auto:recursive_character",
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.source_file == "manual.md"
    assert chunk.header == "Setup"
    assert chunk.path == ("Setup",)
    assert chunk.metadata["manual_id"] == "coffee"
    assert chunk.metadata["tags"] == ["setup"]
    assert chunk.metadata["langchain_source"] == "manual.md"
    assert chunk.metadata["page_start"] == 1
    assert chunk.metadata["page_end"] == 1
    assert chunk.metadata["parser_profile"] == "langchain:md:auto:recursive_character"
    assert chunk.metadata["langchain_adapter_version"] == "1"
    assert chunk.metadata["chunk_id"].startswith("chunk:sha256:")
    assert chunk.metadata["element_ids"][0].startswith("element:sha256:")


def test_documents_to_chunks_skips_blank_documents(tmp_path):
    chunks = documents_to_chunks(
        [_FakeDocument(page_content="   ", metadata={})],
        source_path=tmp_path / "manual.txt",
    )

    assert chunks == []


def test_chunk_stats_use_hashes_not_raw_text():
    secret_text = "Raw secret boiler reset procedure should not appear."
    chunks = [
        Chunk(
            text=secret_text,
            header="Reset",
            path=("Reset",),
            level=1,
            start_line=1,
            source_file="manual.md",
            metadata={"parser_profile": "markdown", "page_start": 3},
        )
    ]

    payload = _stats(chunks).to_dict()

    assert payload["count"] == 1
    assert payload["page_coverage_count"] == 1
    assert payload["parser_profiles"] == ["markdown"]
    assert secret_text not in str(payload)
    assert len(payload["text_hash_samples"][0]) == 16
