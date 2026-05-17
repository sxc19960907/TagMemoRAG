from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator
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
    ann_preselect_enabled: bool = False
    ann_candidate_k: int = 64
    ann_force_exact_on_filters: bool = False
    debug_metadata_enabled: bool = False
    lexical_enabled: bool = True
    lexical_candidate_k: int = 32
    lexical_source_k: int = 3
    lexical_min_token_chars: int = 2
    lexical_boost: float = 0.2
    lexical_exact_code_boost: float = 0.15
    lexical_model_boost: float = 0.12
    metadata_narrowing_enabled: bool = True
    metadata_narrowing_brand_policy: Literal["boost_if_not_unique", "hard_filter", "boost"] = "boost_if_not_unique"
    metadata_narrowing_category_policy: Literal["hard_filter_product_manual", "hard_filter", "boost"] = "hard_filter_product_manual"
    metadata_narrowing_min_candidates: int = Field(default=1, ge=1)


class ParserConfig(BaseModel):
    max_chars: int = 500
    min_chars: int = 50
    overlap_chars: int = Field(default=0, ge=0)
    pdf_profile: Literal["product_manual", "generic"] = "product_manual"
    pdf_heading_hints: list[str] = Field(default_factory=list)


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
    incremental_auto_max_dirty_manuals: int = 20
    incremental_auto_max_dirty_chunks: int = 500
    rebuild_queue_enabled: bool = False
    rebuild_queue_durable: bool = False
    rebuild_queue_max_workers: int = 1
    rebuild_queue_max_attempts: int = 2
    rebuild_queue_retry_backoff_seconds: float = 5.0
    rebuild_queue_history_limit: int = 100
    registry_backend: Literal["file", "sqlite"] = "file"
    registry_path: str = "data/manual_registry.sqlite3"
    blob_backend: Literal["local", "s3"] = "local"
    blob_root_dir: str = "data/manual_blobs"
    s3_bucket: str = ""
    s3_prefix: str = ""
    s3_endpoint_url: str = ""
    s3_region: str = ""
    s3_access_key_env: str = "AWS_ACCESS_KEY_ID"
    s3_secret_key_env: str = "AWS_SECRET_ACCESS_KEY"
    s3_session_token_env: str = ""
    s3_addressing_style: Literal["auto", "virtual", "path"] = "auto"
    s3_timeout_seconds: float = 10.0


class WavePhase0Config(BaseModel):
    enabled: bool = True
    epa_basis_enabled: bool = True
    epa_min_k: int = Field(default=8, ge=1)
    epa_cluster_count: int = Field(default=32, ge=1)
    epa_energy_threshold: float = Field(default=0.95, gt=0.0, le=1.0)
    epa_retrain_growth_ratio: float = Field(default=0.20, ge=0.0)
    epa_lock_timeout_seconds: float = Field(default=30.0, gt=0.0)


class WavePhase1Config(BaseModel):
    enabled: bool = True
    spike_enabled: bool = False
    cooccurrence_enabled: bool = True

    # Co-occurrence builder (mirror VCPToolBox PHI_MAX/PHI_MIN/LEGACY_PHI)
    phi_max: float = Field(default=0.9, gt=0.0, le=1.0)
    phi_min: float = Field(default=0.5, ge=0.0, le=1.0)
    legacy_phi: float = Field(default=0.7, ge=0.0, le=1.0)
    max_tags_per_manual: int = Field(default=100, ge=2)

    # Spike propagation (mirror srConfig defaults from TagMemoEngine.js:187-195)
    spike_max_hops: int = Field(default=4, ge=1)
    spike_base_momentum: float = Field(default=2.0, ge=0.0)
    spike_firing_threshold: float = Field(default=0.10, ge=0.0)
    spike_base_decay: float = Field(default=0.25, gt=0.0, le=1.0)
    spike_wormhole_decay: float = Field(default=0.70, gt=0.0, le=1.0)
    spike_tension_threshold: float = Field(default=1.0, gt=0.0)
    spike_max_emergent_nodes: int = Field(default=50, ge=1)
    spike_max_neighbors_per_node: int = Field(default=20, ge=1)

    # Seed selection (top-K cosine substitute for ResidualPyramid in Phase 1)
    seed_top_k: int = Field(default=8, ge=1)
    seed_min_similarity: float = Field(default=0.3, ge=0.0, le=1.0)

    # Boost factor strategy (D2/D5: constant=1.0 default; "epa" = Phase 2a logicDepth*scale;
    # "pyramid" = Phase 2b-1 full source formula via ResidualPyramid features).
    dynamic_boost_factor_strategy: Literal["constant", "epa", "pyramid"] = "constant"
    dynamic_boost_min: float = Field(default=0.3, ge=0.0)
    dynamic_boost_max: float = Field(default=2.0, gt=0.0)

    # Phase 2a: EPA dynamic boost shape — `dynamic = max(epa_floor, logicDepth * scale)`.
    # Defaults (1.0 / 0.0) keep behavior equivalent to Phase 1 strategy="epa" path.
    # D4: also applied as post-multiplier/floor to strategy="pyramid" output for ops escape hatch.
    epa_logic_depth_scale: float = Field(default=1.0, ge=0.0)
    epa_floor: float = Field(default=0.0, ge=0.0)

    # Phase 2b-1: ResidualPyramid (multi-level Gram-Schmidt) seed selector + full
    # dynamicBoostFactor formula. See ResidualPyramid source defaults.
    pyramid_max_levels: int = Field(default=3, ge=1, le=10)
    pyramid_top_k: int = Field(default=10, ge=1, le=100)
    pyramid_min_energy_ratio: float = Field(default=0.1, gt=0.0, le=1.0)
    pyramid_layer_decay_base: float = Field(default=0.7, gt=0.0, le=1.0)
    pyramid_use_handshake_features: bool = Field(default=True)
    activation_multiplier_min: float = Field(default=0.5, ge=0.0)
    activation_multiplier_max: float = Field(default=1.5, ge=0.0)
    # Post-scale applied AFTER the full pyramid dynamicBoostFactor formula.
    # Default 1.0 keeps the formula numerically equivalent to VCP source
    # (TagMemoEngine.js:88 has no post-scale; this knob exists only as an
    # ops escape hatch for deployment-specific tuning, never as a fixture
    # calibration handle).
    pyramid_post_scale: float = Field(default=1.0, ge=0.0)

    # Phase 2b-2: external modulators (langPenalty + coreBoost). Defaults preserve
    # Phase 2b-1 behavior (lang_penalty_enabled=False ⇒ all helpers return 1.0).
    # Source defaults: TagMemoEngine.js:140-180 (penaltyUnknown=0.4, penaltyCrossDomain=0.3,
    # coreBoostRange=[1.20, 1.40]).
    lang_penalty_enabled: bool = False
    lang_penalty_unknown: float = Field(default=0.4, ge=0.0, le=1.0)
    lang_penalty_cross_domain: float = Field(default=0.3, ge=0.0, le=1.0)
    core_boost_min: float = Field(default=1.20, ge=1.0)
    core_boost_max: float = Field(default=1.40, ge=1.0)

    # Phase 3: V6 detectCrossDomainResonance. Default off — when enabled, the
    # pyramid dynamicBoostFactor formula's `resonance` term stops being stubbed
    # at 0 and instead reads cross-axis co-activation from the EPA dominantAxes.
    # Source: lioensky/VCPToolBox EPAModule.js:170-201 (commit aff66193).
    cross_domain_resonance_enabled: bool = False

    # Phase 3.5: true tag-intrinsic residual energy producer/consumer. Producer
    # can write rows during rebuild, while this flag keeps online consumers off
    # by default for baseline compatibility.
    intrinsic_residuals_enabled: bool = False
    intrinsic_residual_top_n: int | None = Field(default=None, ge=1, le=100)

    # Phase 4: V8 geodesicRerank — reranks wave_search candidates by tag energy
    # field accumulated during spike propagation. Default off; when enabled and
    # spike_enabled is true, execute_search oversamples wave_search candidates
    # (top_k * geodesic_oversample_factor), reranks via tag-energy mean per
    # chunk, then truncates to top_k. minGeoSamples differs from source default
    # (4) because this repo's manuals carry ~3 tags/chunk on average.
    geodesic_rerank_enabled: bool = False
    geodesic_alpha: float = Field(default=0.3, ge=0.0, le=1.0)
    geodesic_oversample_factor: float = Field(default=2.0, ge=1.0)
    geodesic_min_geo_samples: int = Field(default=2, ge=1)

    # Semantic dedup
    dedup_threshold: float = Field(default=0.88, ge=0.0, le=1.0)
    dedup_weight_transfer: float = Field(default=0.2, ge=0.0, le=1.0)

    # Compatibility (D3: chunk-side tag_boost is silenced when spike is on)
    legacy_chunk_tag_boost: bool = False

    @model_validator(mode="after")
    def _validate_core_boost_range(self) -> "WavePhase1Config":
        if self.core_boost_max < self.core_boost_min:
            raise ValueError(
                f"core_boost_max ({self.core_boost_max}) must be >= core_boost_min ({self.core_boost_min})"
            )
        return self


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
    wave_phase0: WavePhase0Config = Field(default_factory=WavePhase0Config)
    wave_phase1: WavePhase1Config = Field(default_factory=WavePhase1Config)
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
