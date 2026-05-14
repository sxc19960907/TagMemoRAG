from __future__ import annotations

import time

import pytest

from tagmemorag.config import ManualLibraryConfig, Settings
from tagmemorag.rebuild_queue import RebuildQueue, is_retryable_error
from tagmemorag.state import AppState, RebuildTask


def _cfg(**kwargs) -> Settings:
    return Settings(
        manual_library=ManualLibraryConfig(
            rebuild_queue_enabled=True,
            rebuild_queue_max_attempts=kwargs.pop("max_attempts", 2),
            rebuild_queue_retry_backoff_seconds=kwargs.pop("backoff", 0.0),
            **kwargs,
        )
    )


def _task(kb_name: str, *, status: str = "done") -> RebuildTask:
    return RebuildTask(task_id=f"task-{time.monotonic_ns()}", status=status, kb_name=kb_name, started_at="now")


def test_same_kb_requests_coalesce_and_full_upgrades():
    queue = RebuildQueue(AppState(), _cfg(), autostart_workers=False)

    first, first_coalesced = queue.enqueue("default", mode="incremental")
    second, second_coalesced = queue.enqueue("default", mode="full")

    assert first_coalesced is False
    assert second_coalesced is True
    assert second.job_id == first.job_id
    assert first.effective_mode == "full"


def test_strict_running_request_gets_followup_job():
    app_state = AppState()
    queue = RebuildQueue(app_state, _cfg(), autostart_workers=False)
    loose, _ = queue.enqueue("default", mode="incremental", allow_fallback=True)
    loose.status = "running"

    strict, coalesced = queue.enqueue("default", mode="incremental", allow_fallback=False)

    assert coalesced is False
    assert strict.job_id != loose.job_id
    assert strict.allow_fallback is False


def test_queued_cancel_marks_terminal_without_running_executor():
    calls = []

    def executor(*args):
        calls.append(args)
        return _task(args[1])

    queue = RebuildQueue(AppState(), _cfg(), executor=executor, autostart_workers=False)
    job, _ = queue.enqueue("default", mode="auto")

    cancelled = queue.cancel(job.job_id)

    assert cancelled.status == "cancelled"
    assert calls == []


def test_retryable_failure_retries_then_succeeds():
    attempts = {"count": 0}

    def executor(app_state, kb_name, cfg, embedder, mode, allow_fallback):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError("qdrant timeout")
        return _task(kb_name)

    queue = RebuildQueue(AppState(), _cfg(max_attempts=2, backoff=0.0), executor=executor, autostart_workers=False)
    job, _ = queue.enqueue("default", mode="full")

    queue.drain_until_idle()

    assert attempts["count"] == 2
    assert queue.get(job.job_id).status == "succeeded"


def test_terminal_invalid_error_does_not_retry():
    attempts = {"count": 0}

    def executor(app_state, kb_name, cfg, embedder, mode, allow_fallback):
        attempts["count"] += 1
        raise ValueError("unsupported suffix")

    queue = RebuildQueue(AppState(), _cfg(max_attempts=3, backoff=0.0), executor=executor, autostart_workers=False)
    job, _ = queue.enqueue("default", mode="full")

    queue.drain_until_idle()

    assert attempts["count"] == 1
    assert queue.get(job.job_id).status == "failed"


def test_retry_classifier_is_conservative():
    assert is_retryable_error(TimeoutError("embedding timeout")) is True
    assert is_retryable_error(ValueError("unsupported suffix")) is False


def test_different_kbs_can_run_independently_when_worker_limit_allows():
    started: list[str] = []

    def executor(app_state, kb_name, cfg, embedder, mode, allow_fallback):
        started.append(kb_name)
        return _task(kb_name)

    queue = RebuildQueue(AppState(), _cfg(rebuild_queue_max_workers=2), executor=executor, autostart_workers=False)
    queue.enqueue("a", mode="full")
    queue.enqueue("b", mode="full")

    queue.drain_until_idle()

    assert started == ["a", "b"]
