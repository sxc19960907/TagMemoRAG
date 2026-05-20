from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tagmemorag.config import Settings, StorageConfig, VectorStoreConfig
from tagmemorag.indexgen import (
    INDEXGEN_META_SCHEMA_VERSION,
    KbMeta,
    KbPaths,
    ReadyGeneration,
)
from tagmemorag.indexgen.meta import GenerationStatus, ShadowGeneration, write_meta
from tagmemorag.replay.generation import (
    ReplayGenerationError,
    load_generation_state,
    resolve_generation_selector,
)
from tagmemorag.storage.json_anchor import JsonAnchorStore
from tagmemorag.storage.json_graph import JsonGraphStore
from tagmemorag.storage.npz_vector import NpzVectorStore
from tagmemorag.types import Anchor


@pytest.fixture
def replay_settings(tmp_path: Path) -> Settings:
    return Settings(storage=StorageConfig(data_dir=str(tmp_path / "data")), model={"dim": 2})


def _ready(build_id: str = "build-g1", retired_at: str | None = None) -> ReadyGeneration:
    return ReadyGeneration(
        created_at="2026-05-19T10:00:00Z",
        swap_at="2026-05-19T10:00:00Z",
        retired_at=retired_at,
        parser_version="p",
        chunker_version="c",
        embedding_model_id="hashing",
        embedding_model_version="v1",
        index_schema_version=1,
        chunk_count=1,
        build_id=build_id,
    )


def _write_meta(cfg: Settings, meta: KbMeta, kb_name: str = "kb-replay") -> None:
    root = Path(cfg.storage.data_dir) / kb_name
    root.mkdir(parents=True, exist_ok=True)
    write_meta(root, meta)


def _seed_generation(cfg: Settings, kb_name: str = "kb-replay", generation: int = 1) -> None:
    paths = KbPaths(kb_name, cfg, generation=generation)
    paths.ensure_generation_root()
    import networkx as nx

    graph = nx.Graph()
    graph.add_node(
        0,
        text="steam milk",
        header="Steam",
        path=["Manual", "Steam"],
        source_file="manual.md",
        start_line=1,
        anchor_key="a1",
        metadata={"chunk_id": "chunk-1"},
    )
    JsonGraphStore(paths.graph).save(graph)
    NpzVectorStore(paths.vectors).add(np.asarray([0]), np.asarray([[1.0, 0.0]], dtype=np.float32))
    JsonAnchorStore(paths.anchors).save([Anchor(anchor_key="a1", label="Steam", node_id=0)], version=7)
    paths.meta.write_text(
        json.dumps(
            {
                "schema_version": cfg.storage.schema_version,
                "model_dim": 2,
                "build_id": f"build-g{generation}",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_resolve_generation_selector_active_and_numeric(replay_settings):
    _write_meta(
        replay_settings,
        KbMeta(
            schema_version=INDEXGEN_META_SCHEMA_VERSION,
            kb_name="kb-replay",
            active_generation=1,
            shadow_generation=None,
            generations={1: _ready()},
        ),
    )

    assert resolve_generation_selector("kb-replay", replay_settings, "active") == 1
    assert resolve_generation_selector("kb-replay", replay_settings, "1") == 1
    assert resolve_generation_selector("kb-replay", replay_settings, "g1") == 1
    assert resolve_generation_selector("kb-replay", replay_settings, 1) == 1


def test_resolve_generation_selector_shadow_ready(replay_settings):
    _write_meta(
        replay_settings,
        KbMeta(
            schema_version=INDEXGEN_META_SCHEMA_VERSION,
            kb_name="kb-replay",
            active_generation=1,
            shadow_generation=2,
            generations={
                1: _ready(),
                2: ShadowGeneration(
                    status=GenerationStatus.READY,
                    progress=1.0,
                    build_started_at="2026-05-19T11:00:00Z",
                    trigger_diff=(),
                ),
            },
        ),
    )

    assert resolve_generation_selector("kb-replay", replay_settings, "shadow") == 2


def test_resolve_generation_selector_rejects_missing_or_not_ready(replay_settings):
    with pytest.raises(ReplayGenerationError, match="index.json"):
        resolve_generation_selector("kb-replay", replay_settings, "active")

    _write_meta(
        replay_settings,
        KbMeta(
            schema_version=INDEXGEN_META_SCHEMA_VERSION,
            kb_name="kb-replay",
            active_generation=1,
            shadow_generation=2,
            generations={
                1: _ready(),
                2: ShadowGeneration(
                    status=GenerationStatus.BUILDING,
                    progress=0.5,
                    build_started_at="2026-05-19T11:00:00Z",
                    trigger_diff=(),
                ),
            },
        ),
    )
    with pytest.raises(ReplayGenerationError, match="not ready"):
        resolve_generation_selector("kb-replay", replay_settings, "shadow")
    with pytest.raises(ReplayGenerationError, match="not found"):
        resolve_generation_selector("kb-replay", replay_settings, "g9")


def test_load_generation_state_loads_artifacts(replay_settings):
    _write_meta(
        replay_settings,
        KbMeta(
            schema_version=INDEXGEN_META_SCHEMA_VERSION,
            kb_name="kb-replay",
            active_generation=1,
            shadow_generation=None,
            generations={1: _ready()},
        ),
    )
    _seed_generation(replay_settings)

    state = load_generation_state("kb-replay", replay_settings, 1)

    assert state.kb_name == "kb-replay"
    assert state.build_id == "build-g1"
    assert state.meta["served_by_generation"] == 1
    assert state.graph.number_of_nodes() == 1
    assert state.vectors.shape == (1, 2)
    assert state.anchors_version == 7
    assert 0 in state.anchors


def test_load_generation_state_rejects_retired_and_missing_artifacts(replay_settings):
    _write_meta(
        replay_settings,
        KbMeta(
            schema_version=INDEXGEN_META_SCHEMA_VERSION,
            kb_name="kb-replay",
            active_generation=1,
            shadow_generation=None,
            generations={1: _ready(retired_at="2026-05-20T00:00:00Z")},
        ),
    )

    with pytest.raises(ReplayGenerationError, match="retired"):
        load_generation_state("kb-replay", replay_settings, 1)

    _write_meta(
        replay_settings,
        KbMeta(
            schema_version=INDEXGEN_META_SCHEMA_VERSION,
            kb_name="kb-replay",
            active_generation=1,
            shadow_generation=None,
            generations={1: _ready()},
        ),
    )
    with pytest.raises(ReplayGenerationError, match="missing graph"):
        load_generation_state("kb-replay", replay_settings, 1)


def test_load_generation_state_rejects_qdrant_provider(replay_settings):
    cfg = replay_settings.model_copy(update={"vector_store": VectorStoreConfig(provider="qdrant")})
    _write_meta(
        cfg,
        KbMeta(
            schema_version=INDEXGEN_META_SCHEMA_VERSION,
            kb_name="kb-replay",
            active_generation=1,
            shadow_generation=None,
            generations={1: _ready()},
        ),
    )

    with pytest.raises(ReplayGenerationError, match="qdrant"):
        load_generation_state("kb-replay", cfg, 1)
