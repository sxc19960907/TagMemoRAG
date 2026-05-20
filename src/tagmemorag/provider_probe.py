from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Iterable

from .answer.base import AnswerPrompt, AnswerRequestContext
from .answer.openai_compatible import OpenAICompatibleAnswerGenerator
from .config import Settings, load_config
from .embedder import create_embedder
from .manual_blob_store import _create_s3_client
from .qdrant_ops import inspect_qdrant
from .reranker.base import RerankDoc
from .reranker.siliconflow import SFQwen3Reranker

PROVIDER_PROBE_SCHEMA_VERSION = "provider_probe.v1"
PROBE_NAMES = ("embedding", "answer", "reranker", "qdrant", "s3")


@dataclass
class ProviderProbeResult:
    name: str
    status: str
    detail: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "detail": dict(self.detail),
        }
        if self.error is not None:
            payload["error"] = dict(self.error)
        return payload


@dataclass
class ProviderProbeReport:
    status: str
    probes: list[ProviderProbeResult]
    schema_version: str = PROVIDER_PROBE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "probes": [probe.to_dict() for probe in self.probes],
        }


def run_provider_probe(
    config_path: str = "config.yaml",
    *,
    selected: Iterable[str] | None = None,
    kb_name: str = "default",
) -> ProviderProbeReport:
    cfg = load_config(config_path)
    selected_set = set(selected or ())
    if not selected_set:
        selected_set = {"all"}
    if "all" in selected_set:
        probe_names = list(PROBE_NAMES)
        explicit = False
    else:
        probe_names = [name for name in PROBE_NAMES if name in selected_set]
        explicit = True
    probes = [_run_one(name, cfg, explicit=explicit, kb_name=kb_name) for name in probe_names]
    return ProviderProbeReport(status=_aggregate_status(probes), probes=probes)


def _run_one(name: str, cfg: Settings, *, explicit: bool, kb_name: str) -> ProviderProbeResult:
    try:
        if name == "embedding":
            return _probe_embedding(cfg, explicit=explicit)
        if name == "answer":
            return _probe_answer(cfg, explicit=explicit)
        if name == "reranker":
            return _probe_reranker(cfg, explicit=explicit)
        if name == "qdrant":
            return _probe_qdrant(cfg, explicit=explicit, kb_name=kb_name)
        if name == "s3":
            return _probe_s3(cfg, explicit=explicit)
    except Exception as exc:  # noqa: BLE001
        return ProviderProbeResult(name, "failed", error=_safe_error(exc))
    return ProviderProbeResult(name, "failed", error={"type": "InvalidProbe", "reason": "unknown_probe"})


def _probe_embedding(cfg: Settings, *, explicit: bool) -> ProviderProbeResult:
    if cfg.model.provider != "http":
        return _not_configured("embedding", explicit, {"provider": cfg.model.provider, "expected_provider": "http"})
    if not _env_present(cfg.model.api_key_env):
        return _missing_env("embedding", cfg.model.api_key_env)
    embedder = create_embedder(
        cfg.model.name,
        cfg.model.device,
        cfg.model.batch_size,
        cfg.model.dim,
        provider=cfg.model.provider,
        base_url=cfg.model.base_url,
        embeddings_url=cfg.model.embeddings_url,
        api_key_env=cfg.model.api_key_env,
        timeout_seconds=_timeout(cfg.model.timeout_seconds),
        dimensions=cfg.model.dimensions,
        normalize=cfg.model.normalize,
    )
    vectors = embedder.encode_batch(["readiness probe"])
    ok = getattr(vectors, "shape", (0, 0))[0] == 1 and getattr(vectors, "shape", (0, 0))[1] > 0
    if not ok:
        return ProviderProbeResult("embedding", "failed", {"provider": "http"}, {"type": "InvalidShape", "reason": "embedding_shape_invalid"})
    return ProviderProbeResult("embedding", "passed", {"provider": "http", "model": cfg.model.name, "dimensions": int(vectors.shape[1])})


def _probe_answer(cfg: Settings, *, explicit: bool) -> ProviderProbeResult:
    if not cfg.answer.enabled or cfg.answer.provider != "openai_compatible":
        return _not_configured(
            "answer",
            explicit,
            {"enabled": cfg.answer.enabled, "provider": cfg.answer.provider, "expected_provider": "openai_compatible"},
        )
    if not _env_present(cfg.answer.api_key_env):
        return _missing_env("answer", cfg.answer.api_key_env)
    generator = OpenAICompatibleAnswerGenerator(cfg)
    generation = generator.generate(
        AnswerRequestContext(
            question="readiness probe",
            retrieve_payload={
                "context_pack": {
                    "items": [
                        {
                            "citation_id": "cit_probe",
                            "content": "Readiness probe evidence.",
                            "source": {"title": "readiness_probe"},
                        }
                    ]
                },
                "citations": [{"citation_id": "cit_probe"}],
            },
            prompt=AnswerPrompt(
                messages=(
                    {"role": "system", "content": "Return one short readiness sentence and cite [cit_probe]."},
                    {"role": "user", "content": "Use the provided evidence to confirm readiness. Evidence: [cit_probe] Readiness probe evidence."},
                ),
                prompt_version=cfg.answer.prompt_version,
                allowed_citation_ids=frozenset({"cit_probe"}),
            ),
            max_output_tokens=256,
        )
    )
    return ProviderProbeResult(
        "answer",
        "passed",
        {
            "provider": cfg.answer.provider,
            "model": generation.model_id or cfg.answer.model_id,
            "text_length": len(generation.text),
            "citation_count": len(generation.citations),
        },
    )


def _probe_reranker(cfg: Settings, *, explicit: bool) -> ProviderProbeResult:
    if not cfg.reranker.enabled or cfg.reranker.provider != "siliconflow":
        return _not_configured(
            "reranker",
            explicit,
            {"enabled": cfg.reranker.enabled, "provider": cfg.reranker.provider, "expected_provider": "siliconflow"},
        )
    if not _env_present(cfg.reranker.api_key_env):
        return _missing_env("reranker", cfg.reranker.api_key_env)
    reranker = SFQwen3Reranker(cfg)
    outcome = reranker.rerank(
        "readiness probe",
        [RerankDoc("doc-a", "alpha readiness"), RerankDoc("doc-b", "beta readiness")],
        cfg.reranker.instruction,
        budget_ms=min(int(cfg.reranker.hard_timeout_ms), 3000),
    )
    return ProviderProbeResult("reranker", "passed", {"provider": cfg.reranker.provider, "items": len(outcome.items)})


def _probe_qdrant(cfg: Settings, *, explicit: bool, kb_name: str) -> ProviderProbeResult:
    if cfg.vector_store.provider != "qdrant":
        return _not_configured("qdrant", explicit, {"provider": cfg.vector_store.provider, "expected_provider": "qdrant"})
    report = inspect_qdrant(kb_name, cfg)
    if report.get("error"):
        return ProviderProbeResult(
            "qdrant",
            "failed",
            {
                "provider": "qdrant",
                "collection_name": report.get("collection_name", ""),
                "collection_exists": bool(report.get("collection_exists")),
            },
            {"type": str(dict(report.get("error") or {}).get("type") or "QdrantProbeError"), "reason": "qdrant_probe_failed"},
        )
    return ProviderProbeResult(
        "qdrant",
        "passed",
        {
            "provider": "qdrant",
            "collection_name": report.get("collection_name", ""),
            "collection_exists": bool(report.get("collection_exists")),
            "graph_loaded": bool(report.get("graph_loaded")),
        },
    )


def _probe_s3(cfg: Settings, *, explicit: bool) -> ProviderProbeResult:
    if cfg.manual_library.blob_backend != "s3":
        return _not_configured("s3", explicit, {"blob_backend": cfg.manual_library.blob_backend, "expected_blob_backend": "s3"})
    if not cfg.manual_library.s3_bucket.strip():
        return ProviderProbeResult("s3", "failed", {"blob_backend": "s3"}, {"type": "InvalidConfig", "reason": "s3_bucket_missing"})
    client = _create_s3_client(cfg)
    client.head_bucket(Bucket=cfg.manual_library.s3_bucket)
    return ProviderProbeResult("s3", "passed", {"blob_backend": "s3", "bucket_configured": True})


def _not_configured(name: str, explicit: bool, detail: dict[str, Any]) -> ProviderProbeResult:
    status = "failed" if explicit else "skipped"
    error = {"type": "NotConfigured", "reason": f"{name}_not_configured"} if explicit else None
    return ProviderProbeResult(name, status, detail, error)


def _missing_env(name: str, env_name: str) -> ProviderProbeResult:
    return ProviderProbeResult(
        name,
        "failed",
        {"env": str(env_name or ""), "present": False},
        {"type": "MissingEnv", "reason": "required_env_var_missing"},
    )


def _env_present(env_name: str) -> bool:
    name = str(env_name or "").strip()
    return bool(name and os.environ.get(name))


def _timeout(value: float) -> float:
    return max(0.1, min(float(value), 5.0))


def _safe_error(exc: Exception) -> dict[str, Any]:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    error: dict[str, Any] = {"type": type(exc).__name__, "reason": _safe_reason(str(exc))}
    if status_code is not None:
        error["status_code"] = int(status_code)
    return error


def _safe_reason(reason: str) -> str:
    value = " ".join(str(reason or "").split())
    return value[:160] or "provider_probe_failed"


def _aggregate_status(probes: list[ProviderProbeResult]) -> str:
    statuses = {probe.status for probe in probes}
    if "failed" in statuses:
        return "failed"
    if "warning" in statuses:
        return "warning"
    if statuses == {"skipped"}:
        return "skipped"
    return "passed"


__all__ = [
    "PROBE_NAMES",
    "PROVIDER_PROBE_SCHEMA_VERSION",
    "ProviderProbeReport",
    "ProviderProbeResult",
    "run_provider_probe",
]
