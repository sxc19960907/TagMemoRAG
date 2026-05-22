from __future__ import annotations

from dataclasses import dataclass
import builtins
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest

from tagmemorag.agentic import AgentStepCtx, ToolObservation
from tagmemorag.agentic.tools import AgentToolRegistry
from tagmemorag.config import ModelConfig, Settings, StorageConfig
from tagmemorag.embedder import HashingEmbedder
from tagmemorag.langchain_adapter.compare import _stats
from tagmemorag.langchain_adapter.loader_splitter import (
    LangChainAdapterUnavailable,
    documents_to_chunks,
    parse_langchain_document,
)
from tagmemorag.langchain_adapter.retriever import (
    TagMemoRAGRetriever,
    retrieve_payload_to_documents,
)
from tagmemorag.langchain_adapter.tools import registry_to_langchain_tools
from tagmemorag.queryplan import build_plan
from tagmemorag.queryplan.budget import BudgetGuard
from tagmemorag.queryplan.plan_log import _reset_shared_writer_for_tests, _shared_writer
from tagmemorag.replay.loader import ReplayPlanLoader
from tagmemorag.state import build_kb
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


def test_retriever_adapter_writes_replayable_queryplan(tmp_path):
    _reset_shared_writer_for_tests()
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model=ModelConfig(provider="hashing", dim=64),
    )
    embedder = HashingEmbedder(dim=64)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# Steam\nWeak steam needs nozzle cleaning.\n", encoding="utf-8")
    state = build_kb(docs, "kb-lc", cfg, embedder=embedder)

    retriever = TagMemoRAGRetriever(state=state, settings=cfg, embedder=embedder)
    payload = retriever.retrieve("weak steam nozzle")
    _shared_writer().flush(timeout=2.0)

    assert payload["plan_id"]
    rows = _read_plans(cfg, "kb-lc")
    assert [row["plan_id"] for row in rows] == [payload["plan_id"]]
    assert rows[0]["cache_status"] == "disabled"
    plans, skipped = ReplayPlanLoader("kb-lc", cfg).load()
    assert skipped == []
    assert [plan.plan_id for plan in plans] == [payload["plan_id"]]
    assert plans[0].query == "weak steam nozzle"


def test_retrieve_payload_to_documents_requires_langchain(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("langchain_core"):
            raise ImportError("simulated missing langchain extra")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(LangChainAdapterUnavailable, match="optional 'langchain' extra"):
        retrieve_payload_to_documents({"results": [{"text": "hello"}]})


def test_registry_to_langchain_tools_requires_langchain(monkeypatch):
    registry = AgentToolRegistry()
    registry.register(_DummyAgentTool())
    cfg = Settings()
    plan = build_plan("q", "kb", cfg)
    ctx = AgentStepCtx(plan=plan, guard=BudgetGuard(plan), settings=cfg, step_idx=0)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("langchain_core"):
            raise ImportError("simulated missing langchain extra")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(LangChainAdapterUnavailable, match="optional 'langchain' extra"):
        registry_to_langchain_tools(registry, ctx)


@dataclass(frozen=True)
class _DummyAgentTool:
    name: str = "dummy"
    description: str = "Dummy tool"
    input_schema: dict[str, Any] | None = None

    def __post_init__(self):
        if self.input_schema is None:
            object.__setattr__(self, "input_schema", {"type": "object", "properties": {}})

    def __call__(self, args: dict[str, Any], ctx: AgentStepCtx) -> ToolObservation:
        return ToolObservation({"args": args, "step_idx": ctx.step_idx})


def _read_plans(cfg: Settings, kb_name: str) -> list[dict[str, Any]]:
    db_path = Path(cfg.storage.data_dir) / kb_name / "query_plans.db"
    deadline = time.monotonic() + 2.0
    while not db_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT plan_id, kb_name, cache_status, evidence_ids_json FROM plans ORDER BY created_at ASC"
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "plan_id": row[0],
            "kb_name": row[1],
            "cache_status": row[2],
            "evidence_ids_json": row[3],
        }
        for row in rows
    ]
