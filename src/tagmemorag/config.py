from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    name: str = "BAAI/bge-small-zh-v1.5"
    dim: int = 384
    device: str = "cpu"
    batch_size: int = 32


class GraphConfig(BaseModel):
    sim_threshold: float = 0.5
    parent_child_bonus: float = 0.2
    sibling_bonus: float = 0.1
    consecutive_bonus: float = 0.15


class SearchConfig(BaseModel):
    top_k: int = 5
    source_k: int = 3
    steps: int = 3
    decay: float = 0.7
    amplitude_cutoff: float = 0.01
    aggregate: Literal["max", "sum"] = "max"
    propagation_boost: float = 1.0


class ParserConfig(BaseModel):
    max_chars: int = 500
    min_chars: int = 50


class StorageConfig(BaseModel):
    data_dir: str = "data"
    schema_version: str = "1"


class Settings(BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    parser: ParserConfig = Field(default_factory=ParserConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)


def load_config(path: str | Path = "config.yaml") -> Settings:
    cfg_path = Path(path)
    if not cfg_path.exists():
        return Settings()
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return Settings.model_validate(data)
