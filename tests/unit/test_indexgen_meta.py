"""Tests for indexgen.meta — KbMeta serialization, invariants, history trimming."""

from __future__ import annotations

from pathlib import Path

import pytest

from tagmemorag.indexgen.meta import (
    INDEXGEN_META_SCHEMA_VERSION,
    GenerationStatus,
    KbMeta,
    ReadyGeneration,
    ShadowGeneration,
    read_meta,
    trim_history,
    write_meta,
)


def _ready(*, swap_at: str = "2026-05-17T10:00:00Z", retired_at: str | None = None) -> ReadyGeneration:
    return ReadyGeneration(
        created_at="2026-05-17T09:00:00Z",
        swap_at=swap_at,
        retired_at=retired_at,
        parser_version="v3",
        chunker_version="v2",
        embedding_model_id="bge-m3",
        embedding_model_version="v1",
        index_schema_version=4,
        chunk_count=1234,
        build_id="20260517100000",
    )


def _shadow(*, status: GenerationStatus = GenerationStatus.BUILDING, progress: float = 0.45) -> ShadowGeneration:
    return ShadowGeneration(
        status=status,
        progress=progress,
        build_started_at="2026-05-17T11:00:00Z",
        trigger_diff=("embedding_model_version",),
        task_id="uuid-task-1",
    )


def test_empty_kb_meta():
    meta = KbMeta.empty("default")
    assert meta.schema_version == INDEXGEN_META_SCHEMA_VERSION
    assert meta.active_generation is None
    assert meta.shadow_generation is None
    assert meta.get_active() is None
    assert meta.get_shadow() is None
    meta.validate_invariants()


def test_round_trip_active_only():
    meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name="default",
        active_generation=2,
        shadow_generation=None,
        generations={1: _ready(retired_at="2026-05-18T00:00:00Z"), 2: _ready()},
    )
    encoded = meta.to_dict()
    decoded = KbMeta.from_dict(encoded)
    assert decoded == meta
    assert decoded.get_active() == _ready()
    assert decoded.get_shadow() is None


def test_round_trip_with_shadow():
    meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name="default",
        active_generation=2,
        shadow_generation=3,
        generations={2: _ready(), 3: _shadow()},
    )
    encoded = meta.to_dict()
    decoded = KbMeta.from_dict(encoded)
    assert decoded == meta
    shadow = decoded.get_shadow()
    assert shadow is not None
    assert shadow.status == GenerationStatus.BUILDING
    assert shadow.progress == pytest.approx(0.45)


def test_from_dict_rejects_unknown_schema_version():
    with pytest.raises(ValueError, match="Unsupported indexgen meta schema_version"):
        KbMeta.from_dict({"schema_version": 999, "kb_name": "x", "active_generation": None, "generations": {}})


def test_invariants_active_must_be_ready():
    meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name="default",
        active_generation=1,
        shadow_generation=None,
        generations={1: _shadow()},  # wrong shape
    )
    with pytest.raises(ValueError, match="ReadyGeneration"):
        meta.validate_invariants()


def test_invariants_shadow_must_be_shadow_shape():
    meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name="default",
        active_generation=1,
        shadow_generation=2,
        generations={1: _ready(), 2: _ready()},
    )
    with pytest.raises(ValueError, match="ShadowGeneration"):
        meta.validate_invariants()


def test_invariants_active_and_shadow_must_differ():
    meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name="default",
        active_generation=1,
        shadow_generation=1,
        generations={1: _ready()},
    )
    with pytest.raises(ValueError, match="must differ"):
        meta.validate_invariants()


def test_read_meta_returns_none_when_missing(tmp_path: Path):
    assert read_meta(tmp_path) is None


def test_read_meta_round_trips_through_disk(tmp_path: Path):
    meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name="default",
        active_generation=2,
        shadow_generation=3,
        generations={2: _ready(), 3: _shadow()},
    )
    write_meta(tmp_path, meta)
    decoded = read_meta(tmp_path)
    assert decoded == meta


def test_read_meta_rejects_corrupt_file(tmp_path: Path):
    (tmp_path / "index.json").write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        read_meta(tmp_path)


def test_trim_history_does_nothing_below_threshold():
    meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name="default",
        active_generation=2,
        shadow_generation=None,
        generations={1: _ready(retired_at="2026-05-18T00:00:00Z"), 2: _ready()},
    )
    trimmed = trim_history(meta, history_max=10)
    assert trimmed.generations.keys() == {1, 2}


def test_trim_history_removes_oldest_retired():
    gens: dict[int, ReadyGeneration | ShadowGeneration] = {
        i: _ready(retired_at=f"2026-05-{i:02d}T00:00:00Z")
        for i in range(1, 6)
    }
    gens[10] = _ready()  # active, never retired
    meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name="default",
        active_generation=10,
        shadow_generation=None,
        generations=gens,
    )
    trimmed = trim_history(meta, history_max=3)
    assert 10 in trimmed.generations  # active protected
    assert len(trimmed.generations) == 3
    # oldest retired removed first (1, 2, 3 are oldest by retired_at)
    assert 1 not in trimmed.generations
    assert 2 not in trimmed.generations
    assert 3 not in trimmed.generations
    assert 4 in trimmed.generations
    assert 5 in trimmed.generations


def test_trim_history_protects_shadow():
    meta = KbMeta(
        schema_version=INDEXGEN_META_SCHEMA_VERSION,
        kb_name="default",
        active_generation=2,
        shadow_generation=3,
        generations={
            1: _ready(retired_at="2026-05-18T00:00:00Z"),
            2: _ready(),
            3: _shadow(),
        },
    )
    trimmed = trim_history(meta, history_max=2)
    assert 2 in trimmed.generations
    assert 3 in trimmed.generations
    assert 1 not in trimmed.generations
