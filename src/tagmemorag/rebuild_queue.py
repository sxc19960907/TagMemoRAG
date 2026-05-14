from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal
import threading
import time
import uuid

from .config import Settings
from .errors import ErrorCode, ServiceError
from .state import AppState, RebuildTask, start_library_rebuild

QUEUE_ACTIVE_STATUSES = {"queued", "retrying", "running", "cancel_requested"}
QUEUE_TERMINAL_STATUSES = {"cancelled", "succeeded", "failed", "abandoned"}
RebuildJobStatus = Literal["queued", "running", "cancel_requested", "cancelled", "succeeded", "failed", "retrying", "abandoned"]
RebuildMode = Literal["full", "incremental", "auto"]


@dataclass
class RebuildJob:
    job_id: str
    kb_name: str
    requested_mode: str
    effective_mode: str
    allow_fallback: bool
    status: RebuildJobStatus
    trigger: str
    priority: int
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    coalesced_into: str | None = None
    task_id: str | None = None
    attempt: int = 0
    max_attempts: int = 1
    next_run_at: str | None = None
    cancel_requested: bool = False
    error: dict[str, Any] | None = None
    operations_summary: dict[str, Any] | None = None

    def to_dict(self, *, coalesced: bool = False, queue_position: int | None = None) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kb_name": self.kb_name,
            "requested_mode": self.requested_mode,
            "effective_mode": self.effective_mode,
            "allow_fallback": self.allow_fallback,
            "status": self.status,
            "trigger": self.trigger,
            "priority": self.priority,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "coalesced_into": self.coalesced_into,
            "task_id": self.task_id,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "next_run_at": self.next_run_at,
            "cancel_requested": self.cancel_requested,
            "error": self.error,
            "operations_summary": self.operations_summary,
            "queue_position": queue_position,
            "coalesced": coalesced,
        }


Executor = Callable[[AppState, str, Settings, Any, str, bool], RebuildTask]


class RebuildQueue:
    def __init__(
        self,
        app_state: AppState,
        cfg: Settings,
        *,
        embedder=None,
        executor: Executor | None = None,
        autostart_workers: bool = True,
    ) -> None:
        self.app_state = app_state
        self.cfg = cfg
        self.embedder = embedder
        self.executor = executor or _default_executor
        self.autostart_workers = autostart_workers
        self._jobs: list[RebuildJob] = []
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._worker_threads: list[threading.Thread] = []
        self._shutdown = False

    def enqueue(
        self,
        kb_name: str,
        *,
        mode: str = "full",
        allow_fallback: bool = True,
        trigger: str = "api",
    ) -> tuple[RebuildJob, bool]:
        _validate_mode(mode)
        now = _now()
        with self._condition:
            existing = self._coalesce_target(kb_name, mode, allow_fallback)
            if existing is not None:
                self._merge(existing, mode, allow_fallback, now)
                self._trim_history_locked()
                self._condition.notify_all()
                return existing, True
            job = RebuildJob(
                job_id=str(uuid.uuid4()),
                kb_name=kb_name,
                requested_mode=mode,
                effective_mode="full" if mode == "full" else mode,
                allow_fallback=allow_fallback,
                status="queued",
                trigger=trigger,
                priority=0,
                created_at=now,
                updated_at=now,
                max_attempts=max(int(self.cfg.manual_library.rebuild_queue_max_attempts), 1),
            )
            self._jobs.append(job)
            self._trim_history_locked()
            if self.autostart_workers:
                self._ensure_workers_locked()
            self._condition.notify_all()
            return job, False

    def list_jobs(self, *, kb_name: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return [
                job.to_dict(queue_position=self._queue_position_locked(job))
                for job in self._jobs
                if (kb_name is None or job.kb_name == kb_name) and (status is None or job.status == status)
            ]

    def get(self, job_id: str) -> RebuildJob:
        with self._lock:
            for job in self._jobs:
                if job.job_id == job_id:
                    return job
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Rebuild job not found.", {"job_id": job_id})

    def inspect(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self.get(job_id)
            return job.to_dict(queue_position=self._queue_position_locked(job))

    def cancel(self, job_id: str) -> RebuildJob:
        now = _now()
        with self._condition:
            job = self.get(job_id)
            if job.status in QUEUE_TERMINAL_STATUSES:
                return job
            job.cancel_requested = True
            job.updated_at = now
            if job.status in {"queued", "retrying"}:
                job.status = "cancelled"
                job.finished_at = now
            else:
                job.status = "cancel_requested"
                if job.task_id:
                    task = self.app_state.rebuild_tasks.get(job.task_id)
                    if task is not None:
                        task.cancel_requested = True
            self._condition.notify_all()
            return job

    def retry(self, job_id: str) -> RebuildJob:
        now = _now()
        with self._condition:
            job = self.get(job_id)
            if job.status != "failed":
                raise ServiceError(ErrorCode.INVALID_REQUEST, "Only failed rebuild jobs can be retried.", {"job_id": job_id, "status": job.status})
            job.status = "queued"
            job.cancel_requested = False
            job.finished_at = None
            job.next_run_at = None
            job.updated_at = now
            job.error = None
            if self.autostart_workers:
                self._ensure_workers_locked()
            self._condition.notify_all()
            return job

    def drain_once(self) -> bool:
        job = self._take_runnable()
        if job is None:
            return False
        self._run_job(job)
        return True

    def drain_until_idle(self, *, timeout_seconds: float = 10.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if not self.drain_once():
                with self._lock:
                    if not any(job.status in {"queued", "retrying", "running", "cancel_requested"} for job in self._jobs):
                        return
                time.sleep(0.01)
        raise TimeoutError("rebuild queue did not become idle")

    def shutdown(self) -> None:
        with self._condition:
            self._shutdown = True
            self._condition.notify_all()
        for thread in list(self._worker_threads):
            thread.join(timeout=1.0)

    def _coalesce_target(self, kb_name: str, mode: str, allow_fallback: bool) -> RebuildJob | None:
        candidates = [job for job in self._jobs if job.kb_name == kb_name and job.status in QUEUE_ACTIVE_STATUSES]
        if not candidates:
            return None
        latest = candidates[-1]
        if latest.status == "running" and latest.allow_fallback and not allow_fallback:
            return None
        return latest

    def _merge(self, job: RebuildJob, mode: str, allow_fallback: bool, now: str) -> None:
        if mode == "full" or job.effective_mode == "full":
            job.requested_mode = "full"
            job.effective_mode = "full"
        elif mode == "incremental" and job.effective_mode == "auto":
            job.requested_mode = "incremental"
            job.effective_mode = "incremental"
        if not allow_fallback:
            job.allow_fallback = False
        job.updated_at = now

    def _ensure_workers_locked(self) -> None:
        max_workers = max(int(self.cfg.manual_library.rebuild_queue_max_workers), 1)
        while len([thread for thread in self._worker_threads if thread.is_alive()]) < max_workers:
            thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker_threads.append(thread)
            thread.start()

    def _worker_loop(self) -> None:
        while True:
            with self._condition:
                while not self._shutdown and self._peek_runnable_locked() is None:
                    self._condition.wait(timeout=0.2)
                if self._shutdown:
                    return
            job = self._take_runnable()
            if job is not None:
                self._run_job(job)

    def _take_runnable(self) -> RebuildJob | None:
        with self._condition:
            job = self._peek_runnable_locked()
            if job is None:
                return None
            now = _now()
            job.status = "running"
            job.started_at = job.started_at or now
            job.updated_at = now
            job.attempt += 1
            return job

    def _peek_runnable_locked(self) -> RebuildJob | None:
        now = datetime.now(timezone.utc)
        running_kbs = {job.kb_name for job in self._jobs if job.status in {"running", "cancel_requested"}}
        running_count = len(running_kbs)
        if running_count >= max(int(self.cfg.manual_library.rebuild_queue_max_workers), 1):
            return None
        for job in self._jobs:
            if job.status not in {"queued", "retrying"}:
                continue
            if job.kb_name in running_kbs:
                continue
            if job.next_run_at and _parse_time(job.next_run_at) > now:
                continue
            return job
        return None

    def _run_job(self, job: RebuildJob) -> None:
        task: RebuildTask | None = None
        try:
            if job.cancel_requested:
                raise _QueueCancelled()
            task = self.executor(self.app_state, job.kb_name, self.cfg, self.embedder, job.effective_mode, job.allow_fallback)
            job.task_id = task.task_id
            while task.status == "running":
                if job.cancel_requested:
                    task.cancel_requested = True
                time.sleep(0.02)
            if task.status == "cancelled":
                raise _QueueCancelled(task.error)
            if task.status != "done":
                raise _TaskFailed(task.error or {"type": "RebuildFailed", "message": "Rebuild task failed."})
            self._mark_succeeded(job, task)
        except _QueueCancelled as exc:
            self._mark_cancelled(job, exc.error)
        except Exception as exc:
            self._mark_failed_or_retrying(job, exc)
        finally:
            with self._condition:
                self._condition.notify_all()

    def _mark_succeeded(self, job: RebuildJob, task: RebuildTask) -> None:
        now = _now()
        with self._condition:
            job.status = "succeeded"
            job.updated_at = now
            job.finished_at = now
            job.error = None
            job.operations_summary = task.to_dict().get("operations_summary")

    def _mark_cancelled(self, job: RebuildJob, error: dict[str, Any] | None = None) -> None:
        now = _now()
        with self._condition:
            job.status = "cancelled"
            job.updated_at = now
            job.finished_at = now
            job.error = error or {"type": "Cancelled", "message": "Rebuild job was cancelled."}

    def _mark_failed_or_retrying(self, job: RebuildJob, exc: Exception) -> None:
        now_dt = datetime.now(timezone.utc)
        error = safe_error(exc)
        retryable = is_retryable_error(exc, error)
        with self._condition:
            if retryable and job.attempt < job.max_attempts and not job.cancel_requested:
                delay = max(float(self.cfg.manual_library.rebuild_queue_retry_backoff_seconds), 0.0)
                job.status = "retrying"
                job.next_run_at = (now_dt + timedelta(seconds=delay)).isoformat()
            else:
                job.status = "failed"
                job.finished_at = now_dt.isoformat()
            job.updated_at = now_dt.isoformat()
            job.error = error

    def _queue_position_locked(self, job: RebuildJob) -> int | None:
        if job.status not in {"queued", "retrying"}:
            return None
        runnable = [item for item in self._jobs if item.kb_name == job.kb_name and item.status in {"queued", "retrying"}]
        try:
            return runnable.index(job) + 1
        except ValueError:
            return None

    def _trim_history_locked(self) -> None:
        limit = max(int(self.cfg.manual_library.rebuild_queue_history_limit), 1)
        terminal = [job for job in self._jobs if job.status in QUEUE_TERMINAL_STATUSES]
        if len(terminal) <= limit:
            return
        remove = set(id(job) for job in terminal[: len(terminal) - limit])
        self._jobs = [job for job in self._jobs if id(job) not in remove]


class _QueueCancelled(Exception):
    def __init__(self, error: dict[str, Any] | None = None):
        super().__init__("Rebuild job was cancelled.")
        self.error = error


class _TaskFailed(Exception):
    def __init__(self, error: dict[str, Any]):
        super().__init__(str(error.get("message") or "Rebuild task failed."))
        self.error = error


def _default_executor(app_state: AppState, kb_name: str, cfg: Settings, embedder, mode: str, allow_fallback: bool) -> RebuildTask:
    return start_library_rebuild(app_state, kb_name, cfg, embedder=embedder, mode=mode, allow_fallback=allow_fallback)


def _validate_mode(mode: str) -> None:
    if mode not in {"full", "incremental", "auto"}:
        raise ServiceError(ErrorCode.INVALID_INPUT, "rebuild mode must be full, incremental, or auto.", {"mode": mode})


def safe_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, _TaskFailed):
        detail = dict(exc.error)
        return {
            "type": str(detail.get("type") or "RebuildFailed"),
            "message": str(detail.get("message") or "Rebuild task failed."),
            "code": detail.get("code"),
        }
    if isinstance(exc, ServiceError):
        return {"type": type(exc).__name__, "code": exc.code.value, "message": exc.message}
    return {"type": type(exc).__name__, "message": str(exc)}


def is_retryable_error(exc: Exception, error: dict[str, Any] | None = None) -> bool:
    payload = error or safe_error(exc)
    code = str(payload.get("code") or "")
    message = str(payload.get("message") or "").lower()
    err_type = str(payload.get("type") or "").lower()
    terminal_terms = ("unsupported suffix", "invalid", "unsafe path", "path traversal", "schema mismatch", "missing required config")
    if any(term in message for term in terminal_terms):
        return False
    if code in {ErrorCode.INVALID_CONFIG.value, ErrorCode.INVALID_INPUT.value, ErrorCode.STORAGE_SCHEMA_MISMATCH.value}:
        return False
    if code == ErrorCode.STORAGE_LOAD_FAILED.value:
        return True
    if code == ErrorCode.EMBEDDING_FAILED.value and any(token in message for token in ("429", "500", "502", "503", "504", "timeout", "timed out")):
        return True
    retry_terms = ("timeout", "timed out", "temporar", "connection", "connectivity", "throttl", "rate limit", "qdrant", "s3")
    return any(term in message or term in err_type for term in retry_terms)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)
