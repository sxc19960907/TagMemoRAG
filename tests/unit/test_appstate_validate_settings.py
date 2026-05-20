"""Tests for AppState.validate_settings_against_index — Slice 8."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tagmemorag.config import Settings, StorageConfig
from tagmemorag.errors import ErrorCode, ServiceError
from tagmemorag.indexgen import (
    INDEXGEN_META_SCHEMA_VERSION,
    KbMeta,
    ReadyGeneration,
)
from tagmemorag.state import AppState


@pytest.fixture
def s_settings(tmp_path: Path) -> Settings:
    return Settings(storage=StorageConfig(data_dir=str(tmp_path / "data")), model={"dim": 64})


def _seed_index_with_versions(
    cfg: Settings,
    kb_name: str,
    *,
    embedding_model_id: str | None = None,
    embedding_model_version: str = "v1",
    index_schema_version: int = 1,
) -> None:
    kb_root = Path(cfg.storage.data_dir) / kb_name
    kb_root.mkdir(parents=True, exist_ok=True)
    g1 = ReadyGeneration(
        created_at="2026-05-17T10:00:00Z",
        swap_at="2026-05-17T10:00:00Z",
        retired_at=None,
        parser_version="default",
        chunker_version="legacy",
        embedding_model_id=embedding_model_id or cfg.model.effective_embedding_model_id,
        embedding_model_version=embedding_model_version,
        index_schema_version=index_schema_version,
        chunk_count=0,
        build_id="g1",
    )
    meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name=kb_name,
        active_generation=1,
        shadow_generation=None,
        generations={1: g1},
    )
    (kb_root / "index.json").write_text(
        json.dumps(meta.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_validate_returns_not_migrated_when_no_index(tmp_path, s_settings):
    app = AppState()
    result = app.validate_settings_against_index("kb-x", s_settings)
    assert result["status"] == "not_migrated"


def test_validate_passes_when_settings_match_active(tmp_path, s_settings):
    _seed_index_with_versions(s_settings, "kb-ok")
    app = AppState()
    result = app.validate_settings_against_index("kb-ok", s_settings)
    assert result["status"] == "ok"
    assert result["active_generation"] == 1


def test_validate_raises_on_embedder_id_mismatch(tmp_path, s_settings):
    _seed_index_with_versions(
        s_settings,
        "kb-bad-id",
        embedding_model_id="qwen3-embedding-8b",
    )
    app = AppState()
    with pytest.raises(ServiceError) as exc_info:
        app.validate_settings_against_index("kb-bad-id", s_settings)
    assert exc_info.value.code == ErrorCode.INDEXGEN_SETTINGS_META_MISMATCH
    fields = [m["field"] for m in exc_info.value.detail["mismatches"]]
    assert "embedding_model_id" in fields


def test_validate_raises_on_version_mismatch(tmp_path, s_settings):
    _seed_index_with_versions(s_settings, "kb-bad-ver", embedding_model_version="v999")
    app = AppState()
    with pytest.raises(ServiceError) as exc_info:
        app.validate_settings_against_index("kb-bad-ver", s_settings)
    assert exc_info.value.code == ErrorCode.INDEXGEN_SETTINGS_META_MISMATCH
    fields = [m["field"] for m in exc_info.value.detail["mismatches"]]
    assert "embedding_model_version" in fields


def test_validate_raises_on_schema_mismatch(tmp_path, s_settings):
    _seed_index_with_versions(s_settings, "kb-bad-schema", index_schema_version=42)
    app = AppState()
    with pytest.raises(ServiceError) as exc_info:
        app.validate_settings_against_index("kb-bad-schema", s_settings)
    assert exc_info.value.code == ErrorCode.INDEXGEN_SETTINGS_META_MISMATCH


def test_validate_reports_all_mismatches_at_once(tmp_path, s_settings):
    _seed_index_with_versions(
        s_settings,
        "kb-many",
        embedding_model_id="other-model",
        embedding_model_version="v999",
        index_schema_version=42,
    )
    app = AppState()
    with pytest.raises(ServiceError) as exc_info:
        app.validate_settings_against_index("kb-many", s_settings)
    fields = [m["field"] for m in exc_info.value.detail["mismatches"]]
    assert set(fields) == {"embedding_model_id", "embedding_model_version", "index_schema_version"}


def test_validate_uses_in_memory_cache_first(tmp_path, s_settings):
    """If generation_meta cache is populated, validate uses it without reading disk."""
    from tagmemorag.indexgen import read_meta

    _seed_index_with_versions(s_settings, "kb-cached")
    app = AppState()
    # Manually populate cache
    meta = read_meta(Path(s_settings.storage.data_dir) / "kb-cached")
    app.set_generation_meta("kb-cached", meta)

    # Corrupt the file on disk; cache should still report ok
    (Path(s_settings.storage.data_dir) / "kb-cached" / "index.json").write_text("{not json}", encoding="utf-8")
    result = app.validate_settings_against_index("kb-cached", s_settings)
    assert result["status"] == "ok"


def test_validate_status_no_active_when_index_empty(tmp_path, s_settings):
    """Empty KB (migrated but no generation built yet) should return no_active_generation."""
    kb_root = Path(s_settings.storage.data_dir) / "kb-empty"
    kb_root.mkdir(parents=True)
    empty_meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name="kb-empty",
        active_generation=None,
        shadow_generation=None,
        generations={},
    )
    (kb_root / "index.json").write_text(
        json.dumps(empty_meta.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    app = AppState()
    result = app.validate_settings_against_index("kb-empty", s_settings)
    assert result["status"] == "no_active_generation"
