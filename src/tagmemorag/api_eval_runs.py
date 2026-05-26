from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from .config import Settings
from .errors import ErrorCode, ServiceError
from .eval.dataset import EvalSuiteError, EvalThresholds
from .eval.runner import run_eval

RUNS_SCHEMA_VERSION = "eval_runs.v1"
SUITES_SCHEMA_VERSION = "eval_suites.v1"
REPORT_DIR = Path(".tmp") / "eval" / "browser-runs"
MAX_ERROR_CHARS = 600


@dataclass(frozen=True)
class BrowserEvalSuite:
    suite_id: str
    name: str
    description: str
    suite_path: str
    docs_path: str
    min_precision_at_k: float | None = None
    min_recall_at_k: float | None = 0.0
    min_mrr: float | None = 0.0
    min_hit_at_k: float | None = 0.0
    top_k: int | None = None
    source_k: int | None = None

    def thresholds(self) -> EvalThresholds:
        return EvalThresholds(
            min_precision_at_k=self.min_precision_at_k,
            min_recall_at_k=self.min_recall_at_k,
            min_mrr=self.min_mrr,
            min_hit_at_k=self.min_hit_at_k,
        )

    def to_dict(self, project_root: Path) -> dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "name": self.name,
            "description": self.description,
            "suite_path": _relative_path(_resolve_project_path(project_root, self.suite_path), project_root),
            "docs_path": _relative_path(_resolve_project_path(project_root, self.docs_path), project_root),
            "thresholds": self.thresholds().to_dict(),
            "top_k": self.top_k,
            "source_k": self.source_k,
        }


@dataclass
class EvalRunJob:
    job_id: str
    suite: BrowserEvalSuite
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    report_path: str = ""
    report_url: str = ""
    summary: dict[str, Any] = field(default_factory=dict)
    error: dict[str, str] | None = None

    def to_dict(self, project_root: Path) -> dict[str, Any]:
        return {
            "schema_version": RUNS_SCHEMA_VERSION,
            "job_id": self.job_id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "suite": self.suite.to_dict(project_root),
            "report_path": self.report_path,
            "report_url": self.report_url,
            "summary": dict(self.summary),
            "error": dict(self.error) if self.error else None,
        }


EVAL_BROWSER_SUITES = {
    "coffee_smoke": BrowserEvalSuite(
        suite_id="coffee_smoke",
        name="Coffee fixture smoke",
        description="Fast local retrieval eval against the checked-in coffee fixture.",
        suite_path="tests/fixtures/eval/coffee.jsonl",
        docs_path="tests/fixtures",
        min_precision_at_k=None,
        min_recall_at_k=0.0,
        min_mrr=0.0,
        min_hit_at_k=0.0,
    )
}


class EvalRunRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tagmemorag-eval")
        self._jobs: dict[str, EvalRunJob] = {}

    def list_suites(self, *, project_root: str | Path | None = None) -> dict[str, Any]:
        root = Path(project_root or Path.cwd()).resolve()
        suites = [suite.to_dict(root) for suite in EVAL_BROWSER_SUITES.values() if _suite_paths_exist(root, suite)]
        return {"schema_version": SUITES_SCHEMA_VERSION, "suites": suites}

    def start_run(self, suite_id: str, *, settings: Settings, project_root: str | Path | None = None) -> dict[str, Any]:
        root = Path(project_root or Path.cwd()).resolve()
        suite = _suite_for_id(suite_id)
        _validate_suite_paths(root, suite)
        with self._lock:
            running = next((job for job in self._jobs.values() if job.status in {"queued", "running"}), None)
            if running is not None:
                raise ServiceError(
                    ErrorCode.REBUILD_IN_PROGRESS,
                    "An eval run is already running.",
                    {"job_id": running.job_id, "suite_id": running.suite.suite_id},
                )
            job = EvalRunJob(job_id=uuid4().hex, suite=suite, status="queued", created_at=_now())
            self._jobs[job.job_id] = job
            self._executor.submit(self._run_job, job.job_id, settings.model_copy(deep=True), root)
            return job.to_dict(root)

    def get_run(self, job_id: str, *, project_root: str | Path | None = None) -> dict[str, Any]:
        root = Path(project_root or Path.cwd()).resolve()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise ServiceError(ErrorCode.INVALID_REQUEST, "Eval run was not found.", {"job_id": job_id})
            return job.to_dict(root)

    def reset_for_tests(self) -> None:
        with self._lock:
            self._jobs.clear()

    def _run_job(self, job_id: str, settings: Settings, project_root: Path) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = _now()
        try:
            suite_path = _resolve_project_path(project_root, job.suite.suite_path)
            docs_path = _resolve_project_path(project_root, job.suite.docs_path)
            report_path = _report_path(project_root, job)
            report = run_eval(
                cfg=settings,
                suite_path=suite_path,
                docs_path=docs_path,
                top_k=job.suite.top_k,
                source_k=job.suite.source_k,
                eval_data_dir=project_root / ".tmp" / "eval" / "browser-data" / job.job_id,
                thresholds=job.suite.thresholds(),
            )
            report.write_json(report_path)
            summary = report.summary.to_dict()
            with self._lock:
                job.report_path = str(report_path)
                job.report_url = "/admin/eval-report?" + urlencode({"report_path": str(report_path)})
                job.summary = summary
                job.status = "passed" if report.summary.passed else "failed"
                job.finished_at = _now()
        except (EvalSuiteError, ServiceError) as exc:
            self._mark_error(job_id, exc)
        except Exception as exc:  # noqa: BLE001
            self._mark_error(job_id, exc)

    def _mark_error(self, job_id: str, exc: Exception) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "error"
            job.finished_at = _now()
            job.error = {"type": type(exc).__name__, "message": _bounded_message(str(exc))}


eval_run_registry = EvalRunRegistry()


def list_eval_suites() -> dict[str, Any]:
    return eval_run_registry.list_suites()


def start_eval_run(suite_id: str, *, settings: Settings) -> dict[str, Any]:
    return eval_run_registry.start_run(suite_id, settings=settings)


def get_eval_run(job_id: str) -> dict[str, Any]:
    return eval_run_registry.get_run(job_id)


def _suite_for_id(suite_id: str) -> BrowserEvalSuite:
    normalized = str(suite_id or "").strip()
    suite = EVAL_BROWSER_SUITES.get(normalized)
    if suite is None:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Unknown eval suite.", {"suite_id": normalized})
    return suite


def _suite_paths_exist(project_root: Path, suite: BrowserEvalSuite) -> bool:
    try:
        _validate_suite_paths(project_root, suite)
    except ServiceError:
        return False
    return True


def _validate_suite_paths(project_root: Path, suite: BrowserEvalSuite) -> None:
    for field_name, value in (("suite_path", suite.suite_path), ("docs_path", suite.docs_path)):
        path = _resolve_project_path(project_root, value)
        if not path.exists():
            raise ServiceError(ErrorCode.INVALID_REQUEST, "Eval suite path is missing.", {"suite_id": suite.suite_id, "field": field_name})


def _resolve_project_path(project_root: Path, value: str) -> Path:
    path = (project_root / value).resolve()
    if not _is_within(path, project_root):
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Eval path must stay inside the project.", {"path": value})
    return path


def _report_path(project_root: Path, job: EvalRunJob) -> Path:
    report_dir = (project_root / REPORT_DIR).resolve()
    if not _is_within(report_dir, project_root):
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Eval report directory must stay inside the project.", {})
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return report_dir / f"{stamp}-{job.job_id[:8]}-{job.suite.suite_id}.json"


def _bounded_message(message: str) -> str:
    text = " ".join(str(message).split())
    return text[:MAX_ERROR_CHARS]


def _relative_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
