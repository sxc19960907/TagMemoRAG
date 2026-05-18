from __future__ import annotations

import pytest
from pydantic import ValidationError

from tagmemorag.config import ParserConfig
from tagmemorag.config import load_config


def test_env_overrides_yaml(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text("server:\n  port: 8000\n", encoding="utf-8")
    monkeypatch.setenv("TAGMEMORAG__SERVER__PORT", "9000")

    assert load_config(config).server.port == 9000


def test_env_overrides_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__SERVER__PORT", "9001")

    assert load_config(tmp_path / "missing.yaml").server.port == 9001


def test_nested_env_delimiter(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__MODEL__NAME", "hashing")

    assert load_config(tmp_path / "missing.yaml").model.name == "hashing"


def test_parser_profile_defaults_to_product_manual():
    cfg = load_config("missing.yaml")

    assert cfg.parser.pdf_profile == "product_manual"
    assert cfg.parser.pdf_heading_hints == []
    assert cfg.parser.overlap_chars == 0


def test_parser_profile_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__PARSER__PDF_PROFILE", "generic")

    assert load_config(tmp_path / "missing.yaml").parser.pdf_profile == "generic"


def test_parser_profile_rejects_unknown_explicit_value():
    with pytest.raises(ValidationError):
        ParserConfig(pdf_profile="unknown")


def test_parser_overlap_rejects_negative_value():
    with pytest.raises(ValidationError):
        ParserConfig(overlap_chars=-1)


def test_http_model_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__MODEL__PROVIDER", "http")
    monkeypatch.setenv("TAGMEMORAG__MODEL__BASE_URL", "https://api.siliconflow.cn/v1")
    monkeypatch.setenv("TAGMEMORAG__MODEL__API_KEY_ENV", "SILICONFLOW_API_KEY")
    monkeypatch.setenv("TAGMEMORAG__MODEL__DIMENSIONS", "4096")

    cfg = load_config(tmp_path / "missing.yaml")

    assert cfg.model.provider == "http"
    assert cfg.model.base_url == "https://api.siliconflow.cn/v1"
    assert cfg.model.api_key_env == "SILICONFLOW_API_KEY"
    assert cfg.model.dimensions == 4096


def test_m2_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__AUTH__ENABLED", "true")
    monkeypatch.setenv("TAGMEMORAG__CACHE__MAX_ENTRIES", "5000")
    monkeypatch.setenv("TAGMEMORAG__RATE_LIMIT__DEFAULT_PER_MINUTE", "120")

    cfg = load_config(tmp_path / "missing.yaml")

    assert cfg.auth.enabled is True
    assert cfg.cache.max_entries == 5000
    assert cfg.rate_limit.default_per_minute == 120


def test_m4_observability_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__OBSERVABILITY__METRICS__ENABLED", "false")
    monkeypatch.setenv("TAGMEMORAG__OBSERVABILITY__TRACING__SAMPLE_RATIO", "0.25")

    cfg = load_config(tmp_path / "missing.yaml")

    assert cfg.observability.metrics.enabled is False
    assert cfg.observability.tracing.sample_ratio == 0.25


def test_assets_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__ASSETS__ENABLED", "true")
    monkeypatch.setenv("TAGMEMORAG__ASSETS__PDF_PAGE_SNAPSHOTS_ENABLED", "true")
    monkeypatch.setenv("TAGMEMORAG__ASSETS__ROOT_DIR", str(tmp_path / "asset-store"))
    monkeypatch.setenv("TAGMEMORAG__ASSETS__EXTRACTOR_VERSION", "pdf_snapshot.test")

    cfg = load_config(tmp_path / "missing.yaml")

    assert cfg.assets.enabled is True
    assert cfg.assets.pdf_page_snapshots_enabled is True
    assert cfg.assets.root_dir == str(tmp_path / "asset-store")
    assert cfg.assets.extractor_version == "pdf_snapshot.test"


def test_vector_store_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__VECTOR_STORE__PROVIDER", "qdrant")
    monkeypatch.setenv("TAGMEMORAG__VECTOR_STORE__QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("TAGMEMORAG__VECTOR_STORE__COLLECTION_PREFIX", "tmr")

    cfg = load_config(tmp_path / "missing.yaml")

    assert cfg.vector_store.provider == "qdrant"
    assert cfg.vector_store.qdrant_url == "http://qdrant:6333"
    assert cfg.vector_store.collection_prefix == "tmr"


def test_manual_library_s3_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__MANUAL_LIBRARY__BLOB_BACKEND", "s3")
    monkeypatch.setenv("TAGMEMORAG__MANUAL_LIBRARY__S3_BUCKET", "tagmemorag-manuals")
    monkeypatch.setenv("TAGMEMORAG__MANUAL_LIBRARY__S3_PREFIX", "/manuals//prod/")
    monkeypatch.setenv("TAGMEMORAG__MANUAL_LIBRARY__S3_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("TAGMEMORAG__MANUAL_LIBRARY__S3_REGION", "us-east-1")
    monkeypatch.setenv("TAGMEMORAG__MANUAL_LIBRARY__S3_ACCESS_KEY_ENV", "MINIO_ROOT_USER")
    monkeypatch.setenv("TAGMEMORAG__MANUAL_LIBRARY__S3_SECRET_KEY_ENV", "MINIO_ROOT_PASSWORD")
    monkeypatch.setenv("TAGMEMORAG__MANUAL_LIBRARY__S3_SESSION_TOKEN_ENV", "AWS_SESSION_TOKEN")
    monkeypatch.setenv("TAGMEMORAG__MANUAL_LIBRARY__S3_ADDRESSING_STYLE", "path")
    monkeypatch.setenv("TAGMEMORAG__MANUAL_LIBRARY__S3_TIMEOUT_SECONDS", "5")

    cfg = load_config(tmp_path / "missing.yaml")

    assert cfg.manual_library.blob_backend == "s3"
    assert cfg.manual_library.s3_bucket == "tagmemorag-manuals"
    assert cfg.manual_library.s3_prefix == "/manuals//prod/"
    assert cfg.manual_library.s3_endpoint_url == "http://localhost:9000"
    assert cfg.manual_library.s3_region == "us-east-1"
    assert cfg.manual_library.s3_access_key_env == "MINIO_ROOT_USER"
    assert cfg.manual_library.s3_secret_key_env == "MINIO_ROOT_PASSWORD"
    assert cfg.manual_library.s3_session_token_env == "AWS_SESSION_TOKEN"
    assert cfg.manual_library.s3_addressing_style == "path"
    assert cfg.manual_library.s3_timeout_seconds == 5


def test_search_ann_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__SEARCH__ANN_PRESELECT_ENABLED", "true")
    monkeypatch.setenv("TAGMEMORAG__SEARCH__ANN_CANDIDATE_K", "32")
    monkeypatch.setenv("TAGMEMORAG__SEARCH__ANN_FORCE_EXACT_ON_FILTERS", "true")
    monkeypatch.setenv("TAGMEMORAG__SEARCH__DEBUG_METADATA_ENABLED", "true")

    cfg = load_config(tmp_path / "missing.yaml")

    assert cfg.search.ann_preselect_enabled is True
    assert cfg.search.ann_candidate_k == 32
    assert cfg.search.ann_force_exact_on_filters is True
    assert cfg.search.debug_metadata_enabled is True


def test_search_lexical_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__SEARCH__LEXICAL_ENABLED", "false")
    monkeypatch.setenv("TAGMEMORAG__SEARCH__LEXICAL_CANDIDATE_K", "12")
    monkeypatch.setenv("TAGMEMORAG__SEARCH__LEXICAL_SOURCE_K", "2")
    monkeypatch.setenv("TAGMEMORAG__SEARCH__LEXICAL_MIN_TOKEN_CHARS", "3")
    monkeypatch.setenv("TAGMEMORAG__SEARCH__LEXICAL_BOOST", "0.04")
    monkeypatch.setenv("TAGMEMORAG__SEARCH__LEXICAL_EXACT_CODE_BOOST", "0.11")
    monkeypatch.setenv("TAGMEMORAG__SEARCH__LEXICAL_MODEL_BOOST", "0.09")

    cfg = load_config(tmp_path / "missing.yaml")

    assert cfg.search.lexical_enabled is False
    assert cfg.search.lexical_candidate_k == 12
    assert cfg.search.lexical_source_k == 2
    assert cfg.search.lexical_min_token_chars == 3
    assert cfg.search.lexical_boost == 0.04
    assert cfg.search.lexical_exact_code_boost == 0.11
    assert cfg.search.lexical_model_boost == 0.09


def test_metrics_public_by_default():
    cfg = load_config("missing.yaml")

    assert "/metrics" in cfg.auth.public_paths


def test_yaml_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("TAGMEMORAG__SERVER__PORT", raising=False)
    config = tmp_path / "config.yaml"
    config.write_text("server:\n  port: 8123\n", encoding="utf-8")

    assert load_config(config).server.port == 8123


def test_phase4_geodesic_rerank_defaults():
    cfg = load_config("missing.yaml")

    assert cfg.wave_phase1.geodesic_rerank_enabled is False
    assert cfg.wave_phase1.geodesic_alpha == 0.3
    assert cfg.wave_phase1.geodesic_oversample_factor == 2.0
    assert cfg.wave_phase1.geodesic_min_geo_samples == 2


def test_phase4_geodesic_rerank_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__WAVE_PHASE1__GEODESIC_RERANK_ENABLED", "true")
    monkeypatch.setenv("TAGMEMORAG__WAVE_PHASE1__GEODESIC_ALPHA", "0.5")
    monkeypatch.setenv("TAGMEMORAG__WAVE_PHASE1__GEODESIC_OVERSAMPLE_FACTOR", "3.0")
    monkeypatch.setenv("TAGMEMORAG__WAVE_PHASE1__GEODESIC_MIN_GEO_SAMPLES", "4")

    cfg = load_config(tmp_path / "missing.yaml")

    assert cfg.wave_phase1.geodesic_rerank_enabled is True
    assert cfg.wave_phase1.geodesic_alpha == 0.5
    assert cfg.wave_phase1.geodesic_oversample_factor == 3.0
    assert cfg.wave_phase1.geodesic_min_geo_samples == 4


def test_phase4_geodesic_rerank_validation_rejects_out_of_range():
    import pytest
    from pydantic import ValidationError

    from tagmemorag.config import WavePhase1Config

    with pytest.raises(ValidationError):
        WavePhase1Config(geodesic_alpha=1.5)
    with pytest.raises(ValidationError):
        WavePhase1Config(geodesic_alpha=-0.1)
    with pytest.raises(ValidationError):
        WavePhase1Config(geodesic_oversample_factor=0.5)
    with pytest.raises(ValidationError):
        WavePhase1Config(geodesic_min_geo_samples=0)


def test_embedding_model_id_defaults_to_name(tmp_path):
    cfg = load_config(tmp_path / "missing.yaml")
    assert cfg.model.embedding_model_id is None
    assert cfg.model.effective_embedding_model_id == cfg.model.name
    assert cfg.model.embedding_model_version == "v1"


def test_embedding_model_id_explicit_override(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__MODEL__EMBEDDING_MODEL_ID", "qwen3-embedding-8b")
    monkeypatch.setenv("TAGMEMORAG__MODEL__EMBEDDING_MODEL_VERSION", "v1.1")
    cfg = load_config(tmp_path / "missing.yaml")
    assert cfg.model.embedding_model_id == "qwen3-embedding-8b"
    assert cfg.model.effective_embedding_model_id == "qwen3-embedding-8b"
    assert cfg.model.embedding_model_version == "v1.1"
