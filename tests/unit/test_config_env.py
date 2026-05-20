from __future__ import annotations

import pytest
from pydantic import ValidationError

from tagmemorag.config import ParserConfig
from tagmemorag.config import load_config
from tagmemorag.config_validation import validate_config
from tagmemorag.provider_probe import run_provider_probe


def test_env_overrides_yaml(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text("server:\n  port: 8000\n", encoding="utf-8")
    monkeypatch.setenv("TAGMEMORAG__SERVER__PORT", "9000")

    assert load_config(config).server.port == 9000


def test_config_validate_local_profile_passes(tmp_path):
    config = tmp_path / "local.yaml"
    config.write_text(
        f"""
model:
  provider: hashing
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
manual_library:
  root_dir: {tmp_path / "manuals"}
  registry_backend: file
  blob_backend: local
  blob_root_dir: {tmp_path / "blobs"}
""",
        encoding="utf-8",
    )

    report = validate_config(config)

    assert report.status == "passed"
    body = report.to_dict()
    assert body["schema_version"] == "config_validation.v1"
    assert body["profile"]["model_provider"] == "hashing"
    assert all(check["status"] == "passed" for check in body["checks"])


def test_provider_probe_all_skips_unconfigured_local_profile():
    report = run_provider_probe("examples/config/local-hashing-npz.yaml", selected=["all"])

    body = report.to_dict()
    assert body["status"] == "skipped"
    assert {probe["status"] for probe in body["probes"]} == {"skipped"}


def test_provider_probe_embedding_fake_passes(tmp_path, monkeypatch):
    import numpy as np
    from tagmemorag import provider_probe

    class FakeEmbedder:
        def encode_batch(self, texts):
            assert texts == ["readiness probe"]
            return np.ones((1, 3), dtype=np.float32)

    def fake_create_embedder(*_args, **_kwargs):
        return FakeEmbedder()

    monkeypatch.setenv("TMR_EMBEDDING_KEY", "secret-value-not-in-output")
    monkeypatch.setattr(provider_probe, "create_embedder", fake_create_embedder)
    config = tmp_path / "http.yaml"
    config.write_text(
        f"""
model:
  provider: http
  name: remote-embedding
  dim: 3
  api_key_env: TMR_EMBEDDING_KEY
storage:
  data_dir: {tmp_path / "data"}
manual_library:
  root_dir: {tmp_path / "manuals"}
  blob_root_dir: {tmp_path / "blobs"}
""",
        encoding="utf-8",
    )

    report = run_provider_probe(str(config), selected=["embedding"])

    body = report.to_dict()
    assert body["status"] == "passed"
    assert body["probes"][0]["detail"]["dimensions"] == 3
    assert "secret-value-not-in-output" not in str(body)


def test_provider_probe_explicit_missing_env_fails(tmp_path, monkeypatch):
    monkeypatch.delenv("TMR_MISSING_PROVIDER_KEY", raising=False)
    config = tmp_path / "answer.yaml"
    config.write_text(
        f"""
model:
  provider: hashing
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
manual_library:
  root_dir: {tmp_path / "manuals"}
  blob_root_dir: {tmp_path / "blobs"}
answer:
  enabled: true
  provider: openai_compatible
  model_id: model
  api_key_env: TMR_MISSING_PROVIDER_KEY
""",
        encoding="utf-8",
    )

    report = run_provider_probe(str(config), selected=["answer"])

    body = report.to_dict()
    assert body["status"] == "failed"
    assert body["probes"][0]["detail"]["env"] == "TMR_MISSING_PROVIDER_KEY"
    assert body["probes"][0]["error"]["reason"] == "required_env_var_missing"


def test_provider_probe_answer_uses_cited_readiness_context(tmp_path, monkeypatch):
    from tagmemorag import provider_probe
    from tagmemorag.answer.base import AnswerCitation, AnswerGeneration

    captured = {}

    class FakeGenerator:
        def __init__(self, cfg):
            captured["model_id"] = cfg.answer.model_id

        def generate(self, context):
            captured["context"] = context
            return AnswerGeneration(
                text="Ready [cit_probe].",
                citations=(AnswerCitation("cit_probe"),),
                model_id="answer-model",
            )

    monkeypatch.setenv("TMR_ANSWER_KEY", "secret-value-not-in-output")
    monkeypatch.setattr(provider_probe, "OpenAICompatibleAnswerGenerator", FakeGenerator)
    config = tmp_path / "answer.yaml"
    config.write_text(
        f"""
model:
  provider: hashing
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
manual_library:
  root_dir: {tmp_path / "manuals"}
  blob_root_dir: {tmp_path / "blobs"}
answer:
  enabled: true
  provider: openai_compatible
  model_id: answer-model
  api_key_env: TMR_ANSWER_KEY
""",
        encoding="utf-8",
    )

    report = run_provider_probe(str(config), selected=["answer"])

    body = report.to_dict()
    assert body["status"] == "passed"
    assert body["probes"][0]["detail"]["text_length"] == len("Ready [cit_probe].")
    assert body["probes"][0]["detail"]["citation_count"] == 1
    context = captured["context"]
    assert context.prompt.allowed_citation_ids == frozenset({"cit_probe"})
    assert context.retrieve_payload["citations"] == [{"citation_id": "cit_probe"}]
    assert context.max_output_tokens == 256
    assert "secret-value-not-in-output" not in str(body)


def test_provider_probe_qdrant_fake_passes(tmp_path, monkeypatch):
    from tagmemorag import provider_probe

    def fake_inspect_qdrant(kb_name, cfg):
        return {
            "collection_name": f"{cfg.vector_store.collection_prefix}_{kb_name}",
            "collection_exists": True,
            "graph_loaded": False,
        }

    monkeypatch.setattr(provider_probe, "inspect_qdrant", fake_inspect_qdrant)
    config = tmp_path / "qdrant.yaml"
    config.write_text(
        f"""
model:
  provider: hashing
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
vector_store:
  provider: qdrant
  collection_prefix: tmr
manual_library:
  root_dir: {tmp_path / "manuals"}
  blob_root_dir: {tmp_path / "blobs"}
""",
        encoding="utf-8",
    )

    report = run_provider_probe(str(config), selected=["qdrant"], kb_name="kb-a")

    assert report.status in {"passed", "warning"}
    assert report.to_dict()["probes"][0]["detail"]["collection_name"] == "tmr_kb-a"


def test_provider_probe_s3_fake_passes(tmp_path, monkeypatch):
    from tagmemorag import provider_probe

    class FakeS3:
        def head_bucket(self, *, Bucket):
            assert Bucket == "tagmemorag-manuals"

    monkeypatch.setenv("TMR_S3_ACCESS", "access-secret")
    monkeypatch.setenv("TMR_S3_SECRET", "secret-secret")
    monkeypatch.setattr(provider_probe, "_create_s3_client", lambda _cfg: FakeS3())
    config = tmp_path / "s3.yaml"
    config.write_text(
        f"""
model:
  provider: hashing
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
manual_library:
  root_dir: {tmp_path / "manuals"}
  registry_backend: sqlite
  registry_path: {tmp_path / "registry.sqlite3"}
  blob_backend: s3
  s3_bucket: tagmemorag-manuals
  s3_access_key_env: TMR_S3_ACCESS
  s3_secret_key_env: TMR_S3_SECRET
""",
        encoding="utf-8",
    )

    report = run_provider_probe(str(config), selected=["s3"])

    body = report.to_dict()
    assert body["status"] == "passed"
    assert body["probes"][0]["detail"]["bucket_configured"] is True
    assert "access-secret" not in str(body)
    assert "secret-secret" not in str(body)


def test_config_validate_missing_remote_env_fails(tmp_path, monkeypatch):
    monkeypatch.delenv("TMR_MISSING_EMBEDDING_KEY", raising=False)
    config = tmp_path / "http.yaml"
    config.write_text(
        f"""
model:
  provider: http
  name: remote-embedding
  dim: 64
  api_key_env: TMR_MISSING_EMBEDDING_KEY
storage:
  data_dir: {tmp_path / "data"}
manual_library:
  root_dir: {tmp_path / "manuals"}
  blob_root_dir: {tmp_path / "blobs"}
""",
        encoding="utf-8",
    )

    report = validate_config(config)

    assert report.status == "failed"
    env_checks = [check for check in report.to_dict()["checks"] if check["name"] == "env_var"]
    assert env_checks[0]["detail"]["env"] == "TMR_MISSING_EMBEDDING_KEY"
    assert env_checks[0]["detail"]["present"] is False
    assert "secret" not in str(report.to_dict()).lower()


def test_config_validate_qdrant_missing_extra_warns(tmp_path, monkeypatch):
    import importlib.util

    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name):
        if name == "qdrant_client":
            return None
        return original_find_spec(name)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    config = tmp_path / "qdrant.yaml"
    config.write_text(
        f"""
model:
  provider: hashing
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
vector_store:
  provider: qdrant
manual_library:
  root_dir: {tmp_path / "manuals"}
  blob_root_dir: {tmp_path / "blobs"}
""",
        encoding="utf-8",
    )

    report = validate_config(config)

    assert report.status == "warning"
    dependency = [check for check in report.to_dict()["checks"] if check["name"] == "dependency"][0]
    assert dependency["status"] == "warning"
    assert dependency["detail"]["dependency"] == "qdrant-client"


def test_config_validate_s3_missing_bucket_fails(tmp_path):
    config = tmp_path / "s3.yaml"
    config.write_text(
        f"""
model:
  provider: hashing
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
manual_library:
  root_dir: {tmp_path / "manuals"}
  registry_backend: sqlite
  registry_path: {tmp_path / "registry.sqlite3"}
  blob_backend: s3
  s3_bucket: ""
  s3_access_key_env: ""
  s3_secret_key_env: ""
""",
        encoding="utf-8",
    )

    report = validate_config(config)

    assert report.status == "failed"
    s3_check = [check for check in report.to_dict()["checks"] if check["name"] == "s3_config"][0]
    assert s3_check["status"] == "failed"
    assert s3_check["detail"]["field"] == "manual_library.s3_bucket"


def test_example_config_profiles_load():
    profiles = [
        "examples/config/local-hashing-npz.yaml",
        "examples/config/local-sqlite-registry.yaml",
        "examples/config/qdrant.yaml",
        "examples/config/s3-blob.yaml",
        "examples/config/answer-openai-compatible.yaml",
        "examples/config/production-provider-verification.yaml",
    ]

    loaded = [load_config(path) for path in profiles]

    assert loaded[0].model.provider == "hashing"
    assert loaded[1].manual_library.registry_backend == "sqlite"
    assert loaded[2].vector_store.provider == "qdrant"
    assert loaded[3].manual_library.blob_backend == "s3"
    assert loaded[4].answer.provider == "openai_compatible"
    assert loaded[5].model.provider == "http"
    assert loaded[5].manual_library.blob_backend == "s3"
    assert loaded[5].reranker.enabled is True
    assert loaded[5].answer.model_id == "deepseek-v4-flash"


def test_production_provider_verification_profile_is_secret_free(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "dummy-siliconflow-token-not-in-output")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-deepseek-token-not-in-output")
    monkeypatch.setenv("TAGMEMORAG_S3_ACCESS_KEY", "tagmemorag")
    monkeypatch.setenv("TAGMEMORAG_S3_SECRET_KEY", "tagmemorag-secret")

    report = validate_config("examples/config/production-provider-verification.yaml")

    serialized = str(report.to_dict())
    assert report.status in {"passed", "warning"}
    assert "SILICONFLOW_API_KEY" in serialized
    assert "DEEPSEEK_API_KEY" in serialized
    assert "dummy-siliconflow-token-not-in-output" not in serialized
    assert "dummy-deepseek-token-not-in-output" not in serialized


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


def test_queryplan_defaults(tmp_path):
    cfg = load_config(tmp_path / "missing.yaml")
    assert cfg.queryplan.persist_enabled is True
    assert cfg.queryplan.retention_days == 30
    assert cfg.queryplan.private_kbs == []
    assert cfg.queryplan.default_latency_ms == 5000
    assert cfg.queryplan.default_max_evidence == 8
    assert cfg.queryplan.default_rerank_tier == "off"
    assert cfg.queryplan.default_allow_external_reranker is True
    assert cfg.queryplan.out_of_scope_keywords is None
    assert cfg.queryplan.pii_mask_rules is None
    assert cfg.queryplan.background_writer_max_queue == 1024


def test_queryplan_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__QUERYPLAN__PERSIST_ENABLED", "false")
    monkeypatch.setenv("TAGMEMORAG__QUERYPLAN__RETENTION_DAYS", "7")
    monkeypatch.setenv("TAGMEMORAG__QUERYPLAN__DEFAULT_LATENCY_MS", "2000")
    cfg = load_config(tmp_path / "missing.yaml")
    assert cfg.queryplan.persist_enabled is False
    assert cfg.queryplan.retention_days == 7
    assert cfg.queryplan.default_latency_ms == 2000


def test_queryplan_yaml_overrides(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "queryplan:\n  retention_days: 90\n  private_kbs: [secret_kb]\n  out_of_scope_keywords: [foo, bar]\n",
        encoding="utf-8",
    )
    cfg = load_config(config)
    assert cfg.queryplan.retention_days == 90
    assert cfg.queryplan.private_kbs == ["secret_kb"]
    assert cfg.queryplan.out_of_scope_keywords == ["foo", "bar"]


def test_reranker_defaults(tmp_path):
    cfg = load_config(tmp_path / "missing.yaml")
    r = cfg.reranker
    assert r.enabled is False
    assert r.default_tier == "tier1"
    assert r.provider == "siliconflow"
    assert r.model_id == "Qwen/Qwen3-Reranker-0.6B"
    assert r.model_version == "v1"
    assert r.top_n == 20
    assert r.rerank_candidates_n == 100
    assert r.calibrator == "minmax"
    assert r.max_seq_length == 32768
    assert r.retry_max == 1
    assert r.circuit_breaker_threshold == 3
    assert r.min_budget_ms == 500
    assert r.hard_timeout_ms == 3000
    assert r.cache_max_entries == 5000


def test_reranker_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMEMORAG__RERANKER__ENABLED", "true")
    monkeypatch.setenv("TAGMEMORAG__RERANKER__TOP_N", "30")
    monkeypatch.setenv("TAGMEMORAG__RERANKER__CALIBRATOR", "zscore")
    cfg = load_config(tmp_path / "missing.yaml")
    assert cfg.reranker.enabled is True
    assert cfg.reranker.top_n == 30
    assert cfg.reranker.calibrator == "zscore"


def test_reranker_yaml_overrides(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "reranker:\n  enabled: true\n  default_tier: tier2\n  rerank_candidates_n: 200\n",
        encoding="utf-8",
    )
    cfg = load_config(config)
    assert cfg.reranker.enabled is True
    assert cfg.reranker.default_tier == "tier2"
    assert cfg.reranker.rerank_candidates_n == 200


def test_reranker_validation_rejects_bad_values():
    import pytest
    from pydantic import ValidationError
    from tagmemorag.config import RerankerConfig

    with pytest.raises(ValidationError):
        RerankerConfig(top_n=0)
    with pytest.raises(ValidationError):
        RerankerConfig(rerank_candidates_n=0)
    with pytest.raises(ValidationError):
        RerankerConfig(circuit_breaker_threshold=0)
    with pytest.raises(ValidationError):
        RerankerConfig(hard_timeout_ms=0)
