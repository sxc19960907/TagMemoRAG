from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

from tagmemorag.config import ModelConfig, SearchConfig, Settings, StorageConfig
from tagmemorag.embedder import HashingEmbedder
from tagmemorag.indexgen import INDEXGEN_META_SCHEMA_VERSION, KbMeta, KbPaths, ReadyGeneration
from tagmemorag.indexgen.meta import write_meta
from tagmemorag.queryplan.plan_log import PLAN_LOG_SCHEMA_VERSION, _SCHEMA_V1_SQL
from tagmemorag.storage.json_anchor import JsonAnchorStore
from tagmemorag.storage.json_graph import JsonGraphStore
from tagmemorag.storage.npz_vector import NpzVectorStore


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "trellis_rag_eval.py"


@pytest.fixture
def replay_settings(tmp_path: Path) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model=ModelConfig(provider="hashing", dim=16),
        search=SearchConfig(steps=0, source_k=1, lexical_enabled=True, metadata_narrowing_enabled=False),
    )


def _ready(generation: int) -> ReadyGeneration:
    return ReadyGeneration(
        created_at="2026-05-19T10:00:00Z",
        swap_at="2026-05-19T10:00:00Z",
        parser_version="p",
        chunker_version="c",
        embedding_model_id="hashing",
        embedding_model_version="v1",
        index_schema_version=1,
        chunk_count=1,
        build_id=f"build-g{generation}",
    )


def _seed_generation(cfg: Settings, *, generation: int, text: str, brand: str = "Acme") -> None:
    import networkx as nx

    paths = KbPaths("kb-replay", cfg, generation=generation)
    paths.ensure_generation_root()
    graph = nx.Graph()
    graph.add_node(
        0,
        text=text,
        header="Manual",
        path=["Manual"],
        source_file="manual.md",
        start_line=1,
        anchor_key=f"a{generation}",
        metadata={"chunk_id": f"chunk-g{generation}", "brand": brand},
    )
    JsonGraphStore(paths.graph).save(graph)
    vectors = HashingEmbedder(dim=cfg.model.dim).encode_batch([text])
    NpzVectorStore(paths.vectors).add(np.asarray([0]), vectors)
    JsonAnchorStore(paths.anchors).save([])
    paths.meta.write_text(
        json.dumps({"schema_version": cfg.storage.schema_version, "model_dim": cfg.model.dim, "build_id": f"build-g{generation}"}),
        encoding="utf-8",
    )


def _write_index(cfg: Settings) -> None:
    root = Path(cfg.storage.data_dir) / "kb-replay"
    root.mkdir(parents=True, exist_ok=True)
    write_meta(
        root,
        KbMeta(
            schema_version=INDEXGEN_META_SCHEMA_VERSION,
            kb_name="kb-replay",
            active_generation=1,
            shadow_generation=None,
            generations={1: _ready(1), 2: _ready(2)},
        ),
    )


def _write_plan_db(cfg: Settings, *, query: str = "steam", filters: dict | None = None) -> None:
    path = Path(cfg.storage.data_dir) / "kb-replay" / "query_plans.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_SCHEMA_V1_SQL)
        conn.execute(f"PRAGMA user_version = {PLAN_LOG_SCHEMA_VERSION}")
        conn.execute(
            """
            INSERT INTO plans (
                plan_id, schema_version, kb_name, query_hash,
                query_rewrites_masked_json, intent, filters_json, strategy_json,
                budget_json, rerank_json, cache_status, evidence_ids_json,
                warnings_json, created_at
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "plan-1",
                "kb-replay",
                "sha256:plan-1",
                json.dumps([query], ensure_ascii=False),
                "text_answer",
                json.dumps(filters or {}),
                json.dumps({"indexes": ["vector"]}),
                json.dumps({"max_evidence": 1}),
                json.dumps({"vendor_used": "noop", "cache_status": "miss", "warnings": ["reranker_fallback:http_500"], "latency_ms": 7}),
                "miss",
                json.dumps(["ev_001"]),
                json.dumps([]),
                "2026-05-19T10:00:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _write_config(tmp_path: Path, cfg: Settings) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "storage": {"data_dir": cfg.storage.data_dir},
                "model": {"provider": "hashing", "dim": cfg.model.dim, "name": cfg.model.name},
                "search": {
                    "steps": cfg.search.steps,
                    "source_k": cfg.search.source_k,
                    "lexical_enabled": cfg.search.lexical_enabled,
                    "metadata_narrowing_enabled": cfg.search.metadata_narrowing_enabled,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _run(tmp_path: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=str(tmp_path),
        text=True,
        capture_output=True,
    )
    return result.returncode, result.stdout


def test_replay_cli_json_output(tmp_path, replay_settings):
    _write_index(replay_settings)
    _seed_generation(replay_settings, generation=1, text="steam milk")
    _seed_generation(replay_settings, generation=2, text="steam milk")
    _write_plan_db(replay_settings)
    cfg_path = _write_config(tmp_path, replay_settings)

    rc, stdout = _run(
        tmp_path,
        "replay",
        "--kb", "kb-replay",
        "--generation", "g2",
        "--baseline", "g1",
        "--config", str(cfg_path),
        "--output-format", "json",
    )

    body = json.loads(stdout)
    assert rc == 0, body
    assert body["schema_version"] == "replay_report.v1"
    assert body["target"]["generation"] == 2
    assert body["baseline"]["generation"] == 1
    assert body["row_counts"]["selected"] == 1
    assert body["rerank_summary"]["fallback_count"] == 1


def test_replay_cli_markdown_output(tmp_path, replay_settings):
    _write_index(replay_settings)
    _seed_generation(replay_settings, generation=1, text="steam milk")
    _write_plan_db(replay_settings)
    cfg_path = _write_config(tmp_path, replay_settings)

    rc, stdout = _run(
        tmp_path,
        "replay",
        "--kb", "kb-replay",
        "--generation", "active",
        "--config", str(cfg_path),
        "--output-format", "markdown",
    )

    assert rc == 0
    assert "# Replay Report: kb-replay" in stdout
    assert "Target Metrics" in stdout


def test_replay_cli_missing_artifact_exits_2(tmp_path, replay_settings):
    cfg_path = _write_config(tmp_path, replay_settings)

    rc, stdout = _run(
        tmp_path,
        "replay",
        "--kb", "missing",
        "--generation", "active",
        "--config", str(cfg_path),
    )

    assert rc == 2
    assert json.loads(stdout)["error"]


def test_replay_cli_regression_exit_code_3(tmp_path, replay_settings):
    _write_index(replay_settings)
    _seed_generation(replay_settings, generation=1, text="steam milk", brand="Acme")
    _seed_generation(replay_settings, generation=2, text="steam milk", brand="Other")
    _write_plan_db(replay_settings, query="steam", filters={"brand": "Acme"})
    cfg_path = _write_config(tmp_path, replay_settings)

    rc, stdout = _run(
        tmp_path,
        "replay",
        "--kb", "kb-replay",
        "--generation", "g2",
        "--baseline", "g1",
        "--config", str(cfg_path),
    )

    body = json.loads(stdout)
    assert rc == 3, body
    assert body["regression_detected"] is True
    assert body["deltas"]["any_hit_rate_delta"] < 0
