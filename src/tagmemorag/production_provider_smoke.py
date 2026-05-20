from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import sqlite3
import tempfile
import time
from typing import Any, Iterable

from fastapi.testclient import TestClient

from . import api
from .config import load_config
from .config_validation import validate_config
from .embedder import create_embedder
from .manual_bulk_import import BulkUploadedFile, commit_bulk_import
from .manual_library import verify_registry_blobs
from .provider_probe import run_provider_probe
from .qdrant_ops import inspect_qdrant
from .queryplan.plan_log import PLAN_LOG_FILENAME
from .state import AppState, load_kb, start_library_rebuild
from .storage.qdrant_vector import collection_name

PROVIDER_SMOKE_SCHEMA_VERSION = "production_provider_smoke.v1"
DEFAULT_PROVIDER_SMOKE_CONFIG = "examples/config/production-provider-verification.yaml"
DEFAULT_PROVIDER_SMOKE_QUESTION = "ASKO W6564 洗衣机排水异常或不排水时应该检查什么？"


@dataclass(frozen=True)
class ProviderSmokeStage:
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


@dataclass(frozen=True)
class ProductionProviderSmokeReport:
    status: str
    config_path: str
    kb_name: str
    workdir: str
    stages: list[ProviderSmokeStage]
    next_steps: list[str]
    schema_version: str = PROVIDER_SMOKE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "config_path": self.config_path,
            "kb_name": self.kb_name,
            "workdir": self.workdir,
            "stages": [stage.to_dict() for stage in self.stages],
            "next_steps": list(self.next_steps),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            "# TagMemoRAG Production Provider Smoke Report",
            "",
            f"- Status: `{self.status}`",
            f"- Config: `{self.config_path}`",
            f"- KB: `{self.kb_name}`",
            f"- Workdir: `{self.workdir}`",
            "",
            "| Stage | Status | Detail |",
            "| --- | --- | --- |",
        ]
        for stage in self.stages:
            detail = _compact_detail(stage.detail)
            if stage.error:
                error = f"{stage.error.get('type', 'Error')}:{stage.error.get('reason', '')}"
                detail = f"{detail}; error={error}".strip("; ")
            lines.append(f"| `{stage.name}` | `{stage.status}` | {detail} |")
        if self.next_steps:
            lines.extend(["", "## Next Steps"])
            lines.extend(f"- {step}" for step in self.next_steps)
        return "\n".join(lines) + "\n"


def run_production_provider_smoke(
    *,
    config_path: str | Path = DEFAULT_PROVIDER_SMOKE_CONFIG,
    kb_name: str = "default",
    manual_paths: Iterable[str | Path] | None = None,
    metadata_path: str | Path | None = None,
    metadata_format: str = "json",
    workdir: str | Path | None = None,
    question: str = DEFAULT_PROVIDER_SMOKE_QUESTION,
    rebuild_mode: str = "full",
    answer_top_k: int = 6,
    answer_source_k: int = 6,
    reset_qdrant_collection: bool = False,
) -> ProductionProviderSmokeReport:
    smoke_workdir = _smoke_workdir(workdir)
    manual_list = [Path(path).expanduser().resolve() for path in (manual_paths or [])]
    stages: list[ProviderSmokeStage] = []

    config_report = validate_config(config_path)
    stages.append(
        ProviderSmokeStage(
            "config_validate",
            config_report.status,
            {
                "profile": dict(config_report.profile),
                "checks": _count_statuses([check.status for check in config_report.checks]),
            },
        )
    )

    provider_report = run_provider_probe(str(config_path), selected=["all"], kb_name=kb_name)
    stages.append(
        ProviderSmokeStage(
            "provider_probe",
            provider_report.status,
            {
                "probes": _count_statuses([probe.status for probe in provider_report.probes]),
                "names": [probe.name for probe in provider_report.probes],
            },
        )
    )

    cfg = load_config(config_path)
    stages.append(_qdrant_reset_stage(kb_name, cfg, reset=reset_qdrant_collection))

    if manual_list:
        try:
            metadata_text, metadata_fmt, metadata_source = _metadata_for_manuals(
                manual_list,
                metadata_path=metadata_path,
                metadata_format=metadata_format,
                workdir=smoke_workdir,
            )
            uploaded = [BulkUploadedFile(filename=path.name, content=path.read_bytes()) for path in manual_list]
            result = commit_bulk_import(
                kb_name,
                metadata_text,
                metadata_fmt,
                uploaded,
                cfg,
                mode="upsert",
                overwrite=True,
            )
            detail = result.to_dict()
            stages.append(
                ProviderSmokeStage(
                    "manual_import",
                    "failed" if result.failed_count else "passed",
                    {
                        "metadata_source": metadata_source,
                        "metadata_format": metadata_fmt,
                        "manual_count": len(manual_list),
                        "imported_count": result.imported_count,
                        "skipped_count": result.skipped_count,
                        "failed_count": result.failed_count,
                        "pending_rebuild": result.pending_rebuild,
                    },
                    _first_failure(detail.get("failures", [])),
                )
            )
        except Exception as exc:  # noqa: BLE001
            stages.append(ProviderSmokeStage("manual_import", "failed", {"manual_count": len(manual_list)}, _safe_error(exc)))
    else:
        stages.append(ProviderSmokeStage("manual_import", "skipped", {"manual_count": 0, "reason": "no_manuals_supplied"}))

    stages.append(_blob_stage(kb_name, cfg))
    stages.append(_rebuild_stage(kb_name, cfg, rebuild_mode=rebuild_mode))
    stages.append(_qdrant_stage(kb_name, cfg))
    answer_stage, reranker_stage = _answer_and_reranker_stages(
        kb_name,
        cfg,
        question=question,
        top_k=answer_top_k,
        source_k=answer_source_k,
    )
    stages.append(reranker_stage)
    stages.append(answer_stage)

    status = _aggregate_status(stages)
    return ProductionProviderSmokeReport(
        status=status,
        config_path=str(config_path),
        kb_name=kb_name,
        workdir=str(smoke_workdir),
        stages=stages,
        next_steps=_next_steps(status, stages),
    )


def write_provider_smoke_report(report: ProductionProviderSmokeReport, path: str | Path, *, fmt: str = "json") -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        text = report.to_json()
    elif fmt == "markdown":
        text = report.to_markdown()
    else:
        raise ValueError("fmt must be 'json' or 'markdown'")
    output_path.write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")


def _metadata_for_manuals(
    manual_paths: list[Path],
    *,
    metadata_path: str | Path | None,
    metadata_format: str,
    workdir: Path,
) -> tuple[str, str, str]:
    if metadata_path is not None:
        path = Path(metadata_path).expanduser().resolve()
        return path.read_text(encoding="utf-8"), metadata_format, str(path)

    rows: list[dict[str, Any]] = []
    for manual in manual_paths:
        sidecar = _sidecar_path(manual)
        if not sidecar.exists():
            raise ValueError(f"metadata sidecar not found for {manual.name}: {sidecar.name}")
        row = json.loads(sidecar.read_text(encoding="utf-8"))
        if not isinstance(row, dict):
            raise ValueError(f"metadata sidecar must contain a JSON object: {sidecar.name}")
        row = dict(row)
        row.pop("checksum", None)
        row["source_file"] = manual.name
        rows.append(row)

    generated = workdir / "manual-metadata.generated.json"
    generated.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return generated.read_text(encoding="utf-8"), "json", str(generated)


def _sidecar_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.metadata.json")


def _qdrant_reset_stage(kb_name: str, cfg, *, reset: bool) -> ProviderSmokeStage:
    target = collection_name(cfg.vector_store.collection_prefix, kb_name)
    detail = {
        "provider": cfg.vector_store.provider,
        "collection_name": target,
        "requested": bool(reset),
    }
    if not reset:
        return ProviderSmokeStage("qdrant_reset", "skipped", detail | {"reason": "not_requested"})
    if cfg.vector_store.provider != "qdrant":
        return ProviderSmokeStage("qdrant_reset", "skipped", detail | {"reason": "vector_store_not_qdrant"})
    try:
        client = _qdrant_client(cfg)
        if not _qdrant_collection_exists(client, target):
            return ProviderSmokeStage("qdrant_reset", "passed", detail | {"action": "absent"})
        client.delete_collection(collection_name=target)
        return ProviderSmokeStage("qdrant_reset", "passed", detail | {"action": "deleted"})
    except Exception as exc:  # noqa: BLE001
        return ProviderSmokeStage("qdrant_reset", "failed", detail, _safe_error(exc))


def _qdrant_client(cfg):
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise RuntimeError("qdrant-client is required to reset Qdrant collections") from exc
    return QdrantClient(url=cfg.vector_store.qdrant_url, timeout=cfg.vector_store.timeout_seconds)


def _qdrant_collection_exists(client, target: str) -> bool:
    collection_exists = getattr(client, "collection_exists", None)
    if callable(collection_exists):
        return bool(collection_exists(target))
    try:
        client.get_collection(collection_name=target)
        return True
    except Exception:
        return False


def _blob_stage(kb_name: str, cfg) -> ProviderSmokeStage:
    try:
        report = verify_registry_blobs(kb_name, cfg)
        missing_count = int(report.get("missing_count") or 0)
        return ProviderSmokeStage(
            "blob_verify",
            "failed" if missing_count else "passed",
            {
                "checked_count": int(report.get("checked_count") or 0),
                "missing_count": missing_count,
                "blob_backend": cfg.manual_library.blob_backend,
            },
            {"type": "MissingBlob", "reason": "registry_blob_missing"} if missing_count else None,
        )
    except Exception as exc:  # noqa: BLE001
        return ProviderSmokeStage("blob_verify", "failed", {"blob_backend": cfg.manual_library.blob_backend}, _safe_error(exc))


def _rebuild_stage(kb_name: str, cfg, *, rebuild_mode: str) -> ProviderSmokeStage:
    try:
        embedder = create_embedder(
            cfg.model.name,
            cfg.model.device,
            cfg.model.batch_size,
            cfg.model.dim,
            provider=cfg.model.provider,
            base_url=cfg.model.base_url,
            embeddings_url=cfg.model.embeddings_url,
            api_key_env=cfg.model.api_key_env,
            timeout_seconds=cfg.model.timeout_seconds,
            dimensions=cfg.model.dimensions,
            normalize=cfg.model.normalize,
        )
        try:
            current = load_kb(kb_name, cfg)
        except Exception:
            current = None
        app_state = AppState(current)
        task = start_library_rebuild(app_state, kb_name, cfg, embedder=embedder, mode=rebuild_mode)
        while task.status == "running":
            time.sleep(0.05)
        detail = task.to_dict()
        return ProviderSmokeStage(
            "manual_library_rebuild",
            "passed" if task.status == "done" else "failed",
            {
                "task_status": task.status,
                "requested_mode": task.requested_mode,
                "effective_mode": task.effective_mode,
                "build_id": task.build_id or "",
                "dirty_manual_count": task.dirty_manual_count,
                "reused_chunk_count": task.reused_chunk_count,
                "embedded_chunk_count": task.embedded_chunk_count,
                "qdrant_sync": _safe_qdrant_sync(task.qdrant_sync),
                "operations_summary": _safe_operations_summary(detail.get("operations_summary")),
            },
            _safe_task_error(task.error),
        )
    except Exception as exc:  # noqa: BLE001
        return ProviderSmokeStage("manual_library_rebuild", "failed", {"requested_mode": rebuild_mode}, _safe_error(exc))


def _qdrant_stage(kb_name: str, cfg) -> ProviderSmokeStage:
    try:
        report = inspect_qdrant(kb_name, cfg)
        error = report.get("error") if isinstance(report.get("error"), dict) else None
        status = "failed" if error else "passed"
        if not report.get("configured"):
            status = "failed"
        return ProviderSmokeStage(
            "qdrant_inspect",
            status,
            {
                "provider": report.get("provider", ""),
                "collection_name": report.get("collection_name", ""),
                "collection_exists": bool(report.get("collection_exists")),
                "graph_loaded": bool(report.get("graph_loaded")),
                "graph_node_count": int(report.get("graph_node_count") or 0),
                "qdrant_point_count": int(report.get("qdrant_point_count") or 0),
                "missing_vector_count": int(report.get("missing_vector_count") or 0),
                "last_qdrant_sync": _safe_qdrant_sync(report.get("last_qdrant_sync")),
                "recommendations": list(report.get("recommendations") or []),
            },
            {"type": str(error.get("type") or "QdrantInspectError"), "reason": "qdrant_inspect_failed"} if error else None,
        )
    except Exception as exc:  # noqa: BLE001
        return ProviderSmokeStage("qdrant_inspect", "failed", {"provider": cfg.vector_store.provider}, _safe_error(exc))


def _answer_and_reranker_stages(kb_name: str, cfg, *, question: str, top_k: int, source_k: int) -> tuple[ProviderSmokeStage, ProviderSmokeStage]:
    try:
        state = load_kb(kb_name, cfg)
        api.settings = cfg
        api.embedder = create_embedder(
            cfg.model.name,
            cfg.model.device,
            cfg.model.batch_size,
            cfg.model.dim,
            provider=cfg.model.provider,
            base_url=cfg.model.base_url,
            embeddings_url=cfg.model.embeddings_url,
            api_key_env=cfg.model.api_key_env,
            timeout_seconds=cfg.model.timeout_seconds,
            dimensions=cfg.model.dimensions,
            normalize=cfg.model.normalize,
        )
        api.app_state = AppState(state)
        api._ANSWER_GENERATOR_CACHE.clear()
        client = TestClient(api.app)
        response = client.post(
            "/answer",
            json={
                "kb_name": kb_name,
                "question": question,
                "top_k": top_k,
                "source_k": source_k,
                "include_retrieve": True,
                "debug": False,
            },
        )
        if response.status_code != 200:
            error = _response_error(response)
            return (
                ProviderSmokeStage("answer_smoke", "failed", {"http_status": response.status_code}, error),
                ProviderSmokeStage("reranker_evidence", "failed", {"plan_id": ""}, error),
            )
        payload = response.json()
        answer = dict(payload.get("answer") or {})
        retrieve = dict(payload.get("retrieve") or {})
        plan_id = str(payload.get("plan_id") or retrieve.get("plan_id") or "")
        reranker_detail = _plan_reranker_detail(cfg, kb_name, plan_id)
        return (
            ProviderSmokeStage(
                "answer_smoke",
                "passed" if answer.get("kind") == "answer" else "failed",
                _summarize_answer_payload(payload),
                None if answer.get("kind") == "answer" else {"type": "AnswerSmokeFailed", "reason": str(answer.get("refusal_reason") or "answer_not_generated")},
            ),
            ProviderSmokeStage(
                "reranker_evidence",
                reranker_detail.pop("status"),
                reranker_detail,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        error = _safe_error(exc)
        return (
            ProviderSmokeStage("answer_smoke", "failed", {"kb_name": kb_name}, error),
            ProviderSmokeStage("reranker_evidence", "failed", {"kb_name": kb_name}, error),
        )


def _summarize_answer_payload(payload: dict[str, Any]) -> dict[str, Any]:
    answer = dict(payload.get("answer") or {})
    retrieve = dict(payload.get("retrieve") or {})
    answer_text = str(answer.get("text") or "")
    answer_citations = answer.get("citations") if isinstance(answer.get("citations"), list) else []
    retrieve_results = retrieve.get("results") if isinstance(retrieve.get("results"), list) else []
    retrieve_citations = retrieve.get("citations") if isinstance(retrieve.get("citations"), list) else []
    answerability = retrieve.get("answerability") if isinstance(retrieve.get("answerability"), dict) else {}
    return {
        "schema_version": str(payload.get("schema_version") or ""),
        "kb_name": str(payload.get("kb_name") or ""),
        "build_id": str(payload.get("build_id") or ""),
        "plan_id": str(payload.get("plan_id") or retrieve.get("plan_id") or ""),
        "answer_kind": str(answer.get("kind") or ""),
        "answer_model_id": str(answer.get("model_id") or ""),
        "answer_text_length": len(answer_text),
        "answer_citation_count": len(answer_citations),
        "retrieve_result_count": len(retrieve_results),
        "retrieve_citation_count": len(retrieve_citations),
        "retrieve_answerable": bool(answerability.get("answerable")),
        "warnings": list(payload.get("warnings") or []),
    }


def _plan_reranker_detail(cfg, kb_name: str, plan_id: str) -> dict[str, Any]:
    detail: dict[str, Any] = {"status": "skipped", "plan_id": plan_id, "reranker_configured": bool(cfg.reranker.enabled)}
    if not plan_id:
        detail["reason"] = "plan_id_missing"
        return detail
    db_path = Path(cfg.storage.data_dir) / kb_name / PLAN_LOG_FILENAME
    if not db_path.exists():
        detail["reason"] = "plan_log_missing"
        return detail
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT rerank_json, warnings_json FROM plans WHERE plan_id = ?", (plan_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        detail["reason"] = "plan_row_missing"
        return detail
    rerank = json.loads(row[0] or "{}")
    warnings = json.loads(row[1] or "[]")
    detail.update(
        {
            "status": "passed" if rerank else "skipped",
            "reranker_id": str(rerank.get("reranker_id") or ""),
            "provider": cfg.reranker.provider,
            "top_n": int(rerank.get("top_n") or 0),
            "warnings": warnings,
        }
    )
    return detail


def _smoke_workdir(workdir: str | Path | None) -> Path:
    if workdir is not None:
        path = Path(workdir).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path(tempfile.mkdtemp(prefix="tagmemorag-provider-smoke-")).resolve()


def _aggregate_status(stages: list[ProviderSmokeStage]) -> str:
    statuses = {stage.status for stage in stages}
    if "failed" in statuses:
        return "failed"
    if "warning" in statuses:
        return "warning"
    return "passed"


def _next_steps(status: str, stages: list[ProviderSmokeStage]) -> list[str]:
    if status == "failed":
        failed = ", ".join(stage.name for stage in stages if stage.status == "failed")
        return [
            f"Investigate failed stage(s): {failed}.",
            "Rerun this smoke after fixing provider credentials, Docker services, or manual import input.",
        ]
    if status == "warning":
        return ["Review warning stages and retain this report with the rollout record."]
    return ["Retain this sanitized report with the production-provider rollout record."]


def _count_statuses(statuses: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1
    return counts


def _first_failure(failures: list[Any]) -> dict[str, Any] | None:
    if not failures:
        return None
    first = failures[0] if isinstance(failures[0], dict) else {}
    return {"type": str(first.get("code") or "BulkImportFailure"), "reason": _safe_reason(str(first.get("message") or "bulk_import_failed"))}


def _safe_task_error(error: dict[str, Any] | None) -> dict[str, Any] | None:
    if not error:
        return None
    return {
        "type": str(error.get("type") or "RebuildError"),
        "reason": _safe_reason(str(error.get("message") or error.get("reason") or "rebuild_failed")),
    }


def _safe_error(exc: Exception) -> dict[str, Any]:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    error: dict[str, Any] = {"type": type(exc).__name__, "reason": _safe_reason(str(exc))}
    if status_code is not None:
        error["status_code"] = int(status_code)
    return error


def _response_error(response) -> dict[str, Any]:
    try:
        body = response.json()
    except Exception:
        body = {}
    return {
        "type": str(body.get("code") or "HttpError"),
        "reason": _safe_reason(str(body.get("message") or f"http_{response.status_code}")),
        "status_code": int(response.status_code),
    }


def _safe_reason(reason: str) -> str:
    value = " ".join(str(reason or "").split())
    return value[:160] or "production_provider_smoke_failed"


def _safe_qdrant_sync(sync: Any) -> dict[str, Any] | None:
    if not isinstance(sync, dict):
        return None
    allowed = {"provider", "strategy", "points_upserted", "points_deleted", "points_reused", "fallback_reason"}
    return {key: sync[key] for key in sorted(allowed) if key in sync}


def _safe_operations_summary(summary: Any) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    allowed = {"created_count", "updated_count", "disabled_count", "deleted_count", "unchanged_count"}
    return {key: summary[key] for key in sorted(allowed) if key in summary}


def _compact_detail(detail: dict[str, Any]) -> str:
    parts = []
    for key, value in detail.items():
        if isinstance(value, dict):
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
        elif isinstance(value, list):
            rendered = ", ".join(str(item) for item in value)
        else:
            rendered = str(value)
        parts.append(f"{key}={rendered}")
    return "<br>".join(parts)


__all__ = [
    "DEFAULT_PROVIDER_SMOKE_CONFIG",
    "DEFAULT_PROVIDER_SMOKE_QUESTION",
    "PROVIDER_SMOKE_SCHEMA_VERSION",
    "ProductionProviderSmokeReport",
    "ProviderSmokeStage",
    "run_production_provider_smoke",
    "write_provider_smoke_report",
]
