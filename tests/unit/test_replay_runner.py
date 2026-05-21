from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tagmemorag.config import ModelConfig, SearchConfig, Settings, StorageConfig
from tagmemorag.indexgen import INDEXGEN_META_SCHEMA_VERSION, KbMeta, KbPaths, ReadyGeneration
from tagmemorag.indexgen.meta import write_meta
from tagmemorag.replay.generation import load_generation_state
from tagmemorag.replay.models import ReplayPlan
from tagmemorag.replay.runner import replay_plan, replay_plans
from tagmemorag.agentic.state import GradeOutcome, StepRecord, ToolObservation
from tagmemorag.queryplan import PlanLog
from tagmemorag.storage.json_anchor import JsonAnchorStore
from tagmemorag.storage.json_graph import JsonGraphStore
from tagmemorag.storage.npz_vector import NpzVectorStore


@pytest.fixture
def replay_settings(tmp_path: Path) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model=ModelConfig(provider="hashing", dim=16),
        search=SearchConfig(steps=0, source_k=1, lexical_enabled=True, metadata_narrowing_enabled=False),
    )


def _ready() -> ReadyGeneration:
    return ReadyGeneration(
        created_at="2026-05-19T10:00:00Z",
        swap_at="2026-05-19T10:00:00Z",
        parser_version="p",
        chunker_version="c",
        embedding_model_id="hashing",
        embedding_model_version="v1",
        index_schema_version=1,
        chunk_count=2,
        build_id="build-g1",
    )


def _seed_generation(cfg: Settings, kb_name: str = "kb-replay") -> None:
    import networkx as nx
    from tagmemorag.embedder import HashingEmbedder

    root = Path(cfg.storage.data_dir) / kb_name
    root.mkdir(parents=True, exist_ok=True)
    write_meta(
        root,
        KbMeta(
            schema_version=INDEXGEN_META_SCHEMA_VERSION,
            kb_name=kb_name,
            active_generation=1,
            shadow_generation=None,
            generations={1: _ready()},
        ),
    )
    paths = KbPaths(kb_name, cfg, generation=1)
    paths.ensure_generation_root()
    graph = nx.Graph()
    graph.add_node(
        0,
        text="steam milk foam",
        header="Steam",
        path=["Manual", "Steam"],
        source_file="manual.md",
        start_line=1,
        anchor_key="a0",
        metadata={"chunk_id": "chunk-steam", "brand": "Acme"},
    )
    graph.add_node(
        1,
        text="clean water filter",
        header="Filter",
        path=["Manual", "Filter"],
        source_file="manual.md",
        start_line=5,
        anchor_key="a1",
        metadata={"chunk_id": "chunk-filter", "brand": "Acme"},
    )
    JsonGraphStore(paths.graph).save(graph)
    embedder = HashingEmbedder(dim=cfg.model.dim)
    vectors = embedder.encode_batch(["steam milk foam", "clean water filter"])
    NpzVectorStore(paths.vectors).add(np.asarray([0, 1]), vectors)
    JsonAnchorStore(paths.anchors).save([])
    paths.meta.write_text(
        json.dumps({"schema_version": cfg.storage.schema_version, "model_dim": cfg.model.dim, "build_id": "build-g1"}),
        encoding="utf-8",
    )


def _plan(query: str = "steam", filters=None) -> ReplayPlan:
    return ReplayPlan(
        plan_id="plan-1",
        kb_name="kb-replay",
        query=query,
        created_at="2026-05-19T10:00:00Z",
        intent="text_answer",
        filters=filters or {},
        budget={"max_evidence": 2},
    )


def test_replay_plan_uses_local_retrieval_stack(replay_settings):
    _seed_generation(replay_settings)
    state = load_generation_state("kb-replay", replay_settings, 1)
    from tagmemorag.embedder import HashingEmbedder

    result = replay_plan(
        plan=_plan("steam"),
        state=state,
        settings=replay_settings,
        generation=1,
        embedder=HashingEmbedder(dim=replay_settings.model.dim),
    )

    assert result.query_replayed is True
    assert result.error == ""
    assert result.result_count >= 1
    assert result.top_chunk_id == "chunk-steam"
    assert result.evidence_ids[0] == "ev_001"


def test_replay_plans_reuses_embedder_for_batch(replay_settings):
    _seed_generation(replay_settings)
    state = load_generation_state("kb-replay", replay_settings, 1)

    results = replay_plans(plans=[_plan("steam"), _plan("filter")], state=state, settings=replay_settings, generation=1)

    assert [r.query_replayed for r in results] == [True, True]
    assert len(results) == 2


def test_replay_plan_records_per_case_errors(replay_settings):
    _seed_generation(replay_settings)
    state = load_generation_state("kb-replay", replay_settings, 1)

    class BrokenEmbedder:
        def encode_query(self, text):
            raise RuntimeError("offline boom")

    result = replay_plan(
        plan=_plan("steam"),
        state=state,
        settings=replay_settings,
        generation=1,
        embedder=BrokenEmbedder(),
    )

    assert result.query_replayed is False
    assert "offline boom" in result.error


def test_replay_plan_uses_agentic_steps_when_present(replay_settings):
    _seed_generation(replay_settings)
    state = load_generation_state("kb-replay", replay_settings, 1)
    plan = _plan("steam")
    plan_log = PlanLog(plan.kb_name, replay_settings)
    plan_log.append_step_async(
        plan.plan_id,
        StepRecord(
            step_idx=0,
            tool="retrieve",
            args={"query": "steam"},
            observation=ToolObservation({"result_count": 1}),
            grade=GradeOutcome(signal="no_signal", reason="c1_stub"),
            decision_source="rule",
            rationale="initial_retrieve",
            ts="2026-05-21T00:00:00Z",
        ),
    )
    plan_log._writer.flush()

    class BrokenEmbedder:
        def encode_query(self, text):
            raise AssertionError("classic replay should not run")

    result = replay_plan(
        plan=plan,
        state=state,
        settings=replay_settings,
        generation=1,
        embedder=BrokenEmbedder(),
    )

    assert result.query_replayed is True
    assert result.result_count == 1
    assert result.error == ""
