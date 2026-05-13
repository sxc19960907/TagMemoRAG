from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class ModelConfig(BaseModel):
    provider: Literal["local", "http", "hashing"] = "local"
    name: str = "BAAI/bge-small-zh-v1.5"
    dim: int = 384
    device: str = "cpu"
    batch_size: int = 32
    base_url: str = "https://api.siliconflow.cn/v1"
    embeddings_url: str | None = None
    api_key_env: str = "SILICONFLOW_API_KEY"
    timeout_seconds: float = 30.0
    dimensions: int | None = None
    normalize: bool = True


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
    metadata_field_boost: float = 0.05
    tag_boost: float = 0.03


class ParserConfig(BaseModel):
    max_chars: int = 500
    min_chars: int = 50


class StorageConfig(BaseModel):
    data_dir: str = "data"
    schema_version: str = "1"


class VectorStoreConfig(BaseModel):
    provider: Literal["npz", "qdrant"] = "npz"
    qdrant_url: str = "http://localhost:6333"
    collection_prefix: str = "tagmemorag"
    timeout_seconds: float = 10.0


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    shutdown_timeout_seconds: int = 60


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: Literal["json", "console"] = "json"


class ApiKeyConfig(BaseModel):
    id: str
    hash: str
    label: str = ""
    kb_allowlist: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=lambda: ["search"])
    rate_limit_per_minute: int | None = None
    created_at: str | None = None
    revoked: bool = False


class AuthConfig(BaseModel):
    enabled: bool = False
    backend: Literal["config", "sqlite"] = "config"
    public_paths: list[str] = Field(
        default_factory=lambda: ["/health", "/ready", "/metrics", "/docs", "/redoc", "/openapi.json"]
    )
    global_max_rate_limit_per_minute: int = 1000
    keys: list[ApiKeyConfig] = Field(default_factory=list)


class RateLimitConfig(BaseModel):
    enabled: bool = True
    default_per_minute: int = 60
    window_seconds: int = 60


class CacheConfig(BaseModel):
    enabled: bool = True
    max_entries: int = 10000
    ttl_seconds: int = 3600


class ManualLibraryConfig(BaseModel):
    root_dir: str = "product_manuals"
    allow_overwrite: bool = False


class MetricsConfig(BaseModel):
    enabled: bool = True
    path: str = "/metrics"
    include_runtime: bool = True


class TracingConfig(BaseModel):
    enabled: bool = False
    service_name: str = "tagmemorag"
    otlp_endpoint: str | None = None
    sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    export_timeout_seconds: float = 5.0


class ObservabilityConfig(BaseModel):
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    tracing: TracingConfig = Field(default_factory=TracingConfig)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TAGMEMORAG__",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    model: ModelConfig = Field(default_factory=ModelConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    parser: ParserConfig = Field(default_factory=ParserConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    manual_library: ManualLibraryConfig = Field(default_factory=ManualLibraryConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return env_settings, dotenv_settings, init_settings, file_secret_settings


def load_config(path: str | Path = "config.yaml") -> Settings:
    cfg_path = Path(path)
    if not cfg_path.exists():
        return Settings()
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return Settings(**data)
