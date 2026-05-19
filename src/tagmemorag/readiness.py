from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import io
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
from typing import Any, Iterator

from . import api
from .config import AnswerConfig, ManualLibraryConfig, SearchConfig, Settings, StorageConfig
from .embedder import HashingEmbedder
from .manual_bundle import export_bundle, import_bundle, inspect_bundle
from .manual_library import list_records, load_manifest, upsert_manual
from .queryplan.plan_log import _reset_shared_writer_for_tests, _shared_writer
from .state import AppState, build_kb

SMOKE_SCHEMA_VERSION = "readiness_smoke.v1"
SMOKE_KB_NAME = "readiness-smoke"


@dataclass
class SmokeCheck:
    name: str
    status: str
    detail: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
        }
        if self.error is not None:
            payload["error"] = self.error
        return payload


@dataclass
class SmokeReport:
    status: str
    checks: list[SmokeCheck]
    workdir: str | None = None
    schema_version: str = SMOKE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "checks": [check.to_dict() for check in self.checks],
            "workdir": self.workdir,
        }


class ReadinessSmokeError(RuntimeError):
    def __init__(self, check_name: str, reason: str, *, detail: dict[str, Any] | None = None):
        super().__init__(reason)
        self.check_name = check_name
        self.reason = reason
        self.detail = detail or {}


def run_readiness_smoke(*, workdir: str | Path | None = None, keep_workdir: bool = False) -> SmokeReport:
    checks: list[SmokeCheck] = []
    workspace, caller_owned = _create_smoke_workspace(workdir)
    retained = keep_workdir or caller_owned
    try:
        _reset_api_state()
        cfg = _smoke_settings(workspace)
        embedder = HashingEmbedder(dim=cfg.model.dim)
        docs = _write_fixture_docs(workspace)

        state = build_kb(docs, SMOKE_KB_NAME, cfg, embedder=embedder)
        _require(state.graph.number_of_nodes() > 0, "build", "no_chunks_built")
        checks.append(SmokeCheck("build", "passed", {"chunks": state.graph.number_of_nodes()}))

        api.settings = cfg
        api.embedder = embedder
        api.app_state = AppState(state)
        with _capture_stdout():
            answer_body = api.answer(
                api.AnswerRequest(
                    question="connector reset button",
                    kb_name=SMOKE_KB_NAME,
                    top_k=1,
                    include_retrieve=True,
                    debug=True,
                ),
                _fake_request(),
                api.ApiKey(id="readiness", label="Readiness", hash="", scopes=frozenset({"search"}), kb_allowlist=()),
                None,
            )
        _require(answer_body["answer"]["kind"] == "answer", "retrieve_answer", "answer_not_generated")
        _require(answer_body["retrieve"]["answerability"]["answerable"] is True, "retrieve_answer", "not_answerable")
        plan_id = str(answer_body.get("plan_id") or "")
        _require(bool(plan_id), "retrieve_answer", "missing_plan_id")
        checks.append(
            SmokeCheck(
                "retrieve_answer",
                "passed",
                {
                    "plan_id": plan_id,
                    "evidence_count": len(answer_body["retrieve"].get("evidence") or []),
                },
            )
        )

        _flush_plan_writer()
        plan_rows = _plan_row_count(cfg, SMOKE_KB_NAME, plan_id)
        _require(plan_rows == 1, "queryplan", "plan_row_missing", {"rows": plan_rows})
        checks.append(SmokeCheck("queryplan", "passed", {"rows": plan_rows}))

        upsert_manual(
            SMOKE_KB_NAME,
            _manual_metadata(),
            b"# Reset Button\nHold the connector reset button for three seconds.\n",
            cfg,
        )
        bundle = workspace / "readiness.bundle.zip"
        exported = export_bundle(SMOKE_KB_NAME, cfg, bundle)
        target_cfg = _smoke_settings(workspace / "bundle-target")
        inspected = inspect_bundle(bundle, target_cfg, target_kb="restored")
        _require(inspected.valid is True, "bundle_roundtrip", "bundle_inspect_failed")
        imported = import_bundle(bundle, target_cfg, target_kb="restored")
        records = list_records("restored", target_cfg)
        manifest = load_manifest("restored", target_cfg)
        _require(imported.imported_count == 1, "bundle_roundtrip", "bundle_import_failed")
        _require(len(records) == 1, "bundle_roundtrip", "bundle_records_missing")
        _require(manifest.pending_changes is True, "bundle_roundtrip", "bundle_dirty_state_missing")
        checks.append(
            SmokeCheck(
                "bundle_roundtrip",
                "passed",
                {
                    "exported_manuals": exported.manual_count,
                    "imported_manuals": imported.imported_count,
                },
            )
        )
        if not retained:
            shutil.rmtree(workspace, ignore_errors=True)
        return SmokeReport(
            status="passed",
            checks=checks,
            workdir=str(workspace) if retained else None,
        )
    except Exception as exc:  # noqa: BLE001
        failed = _failure_check(exc)
        if not any(check.name == failed.name and check.status == "failed" for check in checks):
            checks.append(failed)
        return SmokeReport(status="failed", checks=checks, workdir=str(workspace))
    finally:
        _reset_api_state()


def _create_smoke_workspace(workdir: str | Path | None) -> tuple[Path, bool]:
    if workdir is not None:
        path = Path(workdir).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path, True
    return Path(tempfile.mkdtemp(prefix="tagmemorag-readiness-")).resolve(), False


def _smoke_settings(root: Path) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(root / "data")),
        model={"provider": "hashing", "name": "hashing", "dim": 64},
        search=SearchConfig(metadata_narrowing_enabled=False),
        answer=AnswerConfig(enabled=True, provider="noop"),
        manual_library=ManualLibraryConfig(
            root_dir=str(root / "manuals"),
            registry_backend="file",
            registry_path=str(root / "manual_registry.sqlite3"),
            blob_backend="local",
            blob_root_dir=str(root / "blobs"),
        ),
    )


def _write_fixture_docs(workspace: Path) -> Path:
    docs = workspace / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "manual.md").write_text(
        "# Reset Button\nHold the connector reset button for three seconds.\n",
        encoding="utf-8",
    )
    (docs / "manual.metadata.json").write_text(
        json.dumps(_manual_metadata(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return docs


def _manual_metadata() -> dict[str, Any]:
    return {
        "manual_id": "readiness-manual",
        "title": "Readiness Manual",
        "source_file": "manual.md",
        "product_category": "readiness",
        "language": "en",
        "tags": ["readiness", "reset"],
    }


def _fake_request() -> Any:
    return SimpleNamespace(state=SimpleNamespace(trace_id="readiness-smoke"))


@contextmanager
def _capture_stdout() -> Iterator[None]:
    original = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = original


def _flush_plan_writer() -> None:
    _shared_writer().flush(timeout=2.0)


def _plan_row_count(cfg: Settings, kb_name: str, plan_id: str) -> int:
    db_path = Path(cfg.storage.data_dir) / kb_name / "query_plans.db"
    if not db_path.exists():
        return 0
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("SELECT COUNT(*) FROM plans WHERE plan_id = ?", (plan_id,)).fetchone()
    return int(row[0] if row else 0)


def _require(condition: bool, check_name: str, reason: str, detail: dict[str, Any] | None = None) -> None:
    if not condition:
        raise ReadinessSmokeError(check_name, reason, detail=detail)


def _failure_check(exc: Exception) -> SmokeCheck:
    if isinstance(exc, ReadinessSmokeError):
        return SmokeCheck(
            exc.check_name,
            "failed",
            detail=dict(exc.detail),
            error={"type": "ReadinessSmokeError", "reason": _safe_reason(exc.reason)},
        )
    return SmokeCheck(
        "unexpected",
        "failed",
        error={"type": type(exc).__name__, "reason": _safe_reason(str(exc))},
    )


def _safe_reason(reason: str) -> str:
    value = " ".join(str(reason).split())
    return value[:160] or "unknown"


def _reset_api_state() -> None:
    _reset_shared_writer_for_tests()
    api._ANSWER_GENERATOR_CACHE.clear()
    api._RERANK_DISPATCHER_CACHE.clear()


__all__ = ["SMOKE_SCHEMA_VERSION", "SmokeCheck", "SmokeReport", "run_readiness_smoke"]
