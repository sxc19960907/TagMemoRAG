"""Tests for scripts/replay_against_generation.py — Slice 9."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tagmemorag.config import Settings, StorageConfig
from tagmemorag.embedder import HashingEmbedder
from tagmemorag.indexgen import (
    INDEXGEN_META_SCHEMA_VERSION,
    KbMeta,
    ReadyGeneration,
)
from tagmemorag.state import AppState, build_kb, save_kb


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "replay_against_generation.py"


@pytest.fixture
def replay_settings(tmp_path: Path) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        model={"dim": 64},
    )


@pytest.fixture
def replay_embedder() -> HashingEmbedder:
    return HashingEmbedder(dim=64)


def _docs(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text(
        "# 操作\n蒸汽功能可以打奶泡。\n# 维护\n清洁滤网。\n",
        encoding="utf-8",
    )
    return docs


def _seed_g1_with_data(tmp_path: Path, cfg: Settings, kb_name: str, embedder) -> None:
    """Build a real KB and lay it out under g1/."""
    docs = _docs(tmp_path)
    state = build_kb(docs, kb_name, cfg, embedder=embedder)
    # Save under g1/ instead of root by temporarily redirecting via simple file moves.
    save_kb(state, cfg)
    kb_root = Path(cfg.storage.data_dir) / kb_name
    g1 = kb_root / "g1"
    g1.mkdir(parents=True, exist_ok=True)
    for fname in ("graph.json", "vectors.npz", "anchors.json", "chunk_identity.json", "meta.json"):
        src = kb_root / fname
        if src.is_file():
            src.rename(g1 / fname)

    # Write index.json
    g1_entry = ReadyGeneration(
        created_at="2026-05-17T10:00:00Z",
        swap_at="2026-05-17T10:00:00Z",
        retired_at=None,
        parser_version="default",
        chunker_version="legacy",
        embedding_model_id=cfg.model.effective_embedding_model_id,
        embedding_model_version=cfg.model.embedding_model_version,
        index_schema_version=int(cfg.storage.schema_version),
        chunk_count=state.graph.number_of_nodes(),
        build_id=state.build_id,
    )
    meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name=kb_name,
        active_generation=1,
        shadow_generation=None,
        generations={1: g1_entry},
    )
    (kb_root / "index.json").write_text(
        json.dumps(meta.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_feedback_jsonl(cfg: Settings, kb_name: str, queries: list[str]) -> None:
    """Inject synthetic feedback rows so the replay script can read them."""
    from tagmemorag.retrieval_feedback import feedback_log_path
    path = feedback_log_path(kb_name, cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        for i, query in enumerate(queries):
            fp.write(json.dumps({
                "feedback_id": f"fb-{i}",
                "kb_name": kb_name,
                "trace_id": f"t-{i}",
                "search_id": f"s-{i}",
                "retrieve_id": "",
                "build_id": "",
                "query": query,
                "outcome": "helpful",
                "created_at": "2026-05-17T10:00:00Z",
            }, ensure_ascii=False) + "\n")


def _write_config_yaml(tmp_path: Path, cfg: Settings) -> Path:
    """Render Settings to a yaml the script can read via load_config."""
    import yaml
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "storage": {"data_dir": cfg.storage.data_dir},
        "model": {"dim": cfg.model.dim, "provider": "hashing"},
    }), encoding="utf-8")
    return cfg_path


def _run_script(cwd: Path, *args: str) -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )
    try:
        body = json.loads(result.stdout)
    except json.JSONDecodeError:
        body = {"raw_stdout": result.stdout, "raw_stderr": result.stderr}
    return result.returncode, body


def test_replay_runs_against_active_generation(tmp_path, replay_settings, replay_embedder):
    _seed_g1_with_data(tmp_path, replay_settings, "kb-replay", replay_embedder)
    _write_feedback_jsonl(replay_settings, "kb-replay", ["蒸汽", "滤网", "打奶泡"])
    cfg_path = _write_config_yaml(tmp_path, replay_settings)

    rc, body = _run_script(tmp_path, "--kb", "kb-replay", "--generation", "1", "--config", str(cfg_path))
    assert rc == 0, body
    assert body["kb"] == "kb-replay"
    assert body["queries_count"] == 3
    assert body["target"]["generation"] == 1
    assert body["target"]["queries_replayed"] == 3
    assert body["target"]["node_count"] > 0


def test_replay_returns_error_when_no_index_json(tmp_path, replay_settings):
    cfg_path = _write_config_yaml(tmp_path, replay_settings)
    rc, body = _run_script(tmp_path, "--kb", "missing", "--generation", "1", "--config", str(cfg_path))
    assert rc == 2
    assert body["error"] == "no_index_json"


def test_replay_with_baseline_reports_delta(tmp_path, replay_settings, replay_embedder):
    _seed_g1_with_data(tmp_path, replay_settings, "kb-delta", replay_embedder)
    # Copy g1 into g2 to simulate identical shadow
    kb_root = Path(replay_settings.storage.data_dir) / "kb-delta"
    g2 = kb_root / "g2"
    g2.mkdir()
    for fname in ("graph.json", "vectors.npz", "anchors.json"):
        src = kb_root / "g1" / fname
        if src.exists():
            (g2 / fname).write_bytes(src.read_bytes())

    _write_feedback_jsonl(replay_settings, "kb-delta", ["蒸汽", "滤网"])
    cfg_path = _write_config_yaml(tmp_path, replay_settings)

    rc, body = _run_script(
        tmp_path,
        "--kb", "kb-delta",
        "--generation", "2",
        "--baseline-generation", "1",
        "--config", str(cfg_path),
    )
    assert rc in {0, 3}, body
    assert "baseline" in body
    assert "target" in body
    assert "any_hit_rate_delta" in body
    # g2 is identical copy → delta should be 0
    assert body["any_hit_rate_delta"] == 0.0
    assert body["regression_detected"] is False


def test_replay_handles_missing_feedback_log(tmp_path, replay_settings, replay_embedder):
    _seed_g1_with_data(tmp_path, replay_settings, "kb-empty", replay_embedder)
    cfg_path = _write_config_yaml(tmp_path, replay_settings)

    rc, body = _run_script(tmp_path, "--kb", "kb-empty", "--generation", "1", "--config", str(cfg_path))
    assert rc == 0
    assert body["queries_count"] == 0
    assert body["target"]["queries_replayed"] == 0
