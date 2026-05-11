from __future__ import annotations

from pathlib import Path

import pytest

from tagmemorag.config import Settings, StorageConfig
from tagmemorag.embedder import HashingEmbedder


@pytest.fixture
def test_config(tmp_path: Path) -> Settings:
    return Settings(storage=StorageConfig(data_dir=str(tmp_path / "data")), model={"dim": 64})


@pytest.fixture
def fake_embedder() -> HashingEmbedder:
    return HashingEmbedder(dim=64)
