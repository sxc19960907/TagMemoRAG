"""Tests for queryplan/plan_log.py — SQLite plan log + BackgroundWriter (T2 Slice 3)."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from tagmemorag.config import Settings, StorageConfig
from tagmemorag.errors import ErrorCode, ServiceError
from tagmemorag.observability.metrics import get_metrics
from tagmemorag.agentic.state import GradeOutcome, StepRecord, ToolObservation
from tagmemorag.queryplan import (
    PLAN_LOG_SCHEMA_VERSION,
    BackgroundWriter,
    PlanLog,
    QueryPlan,
    build_plan,
    prune_expired,
)
from tagmemorag.queryplan.plan_log import _ensure_schema, _reset_shared_writer_for_tests


@pytest.fixture
def s_settings(tmp_path: Path) -> Settings:
    return Settings(storage=StorageConfig(data_dir=str(tmp_path / "data")))


@pytest.fixture(autouse=True)
def _reset_writer():
    _reset_shared_writer_for_tests()
    yield
    _reset_shared_writer_for_tests()


def _flush(plan_log: PlanLog, timeout: float = 2.0) -> None:
    """Block until queued updates have been processed."""
    plan_log._writer.flush(timeout=timeout)


# ---------- schema migration ----------

def test_schema_migration_creates_v1_on_fresh_db(tmp_path, s_settings):
    log = PlanLog("kb-x", s_settings)
    _ = log._get_conn()
    db_path = Path(s_settings.storage.data_dir) / "kb-x" / "query_plans.db"
    assert db_path.exists()
    conn = sqlite3.connect(str(db_path))
    try:
        ver = conn.execute("PRAGMA user_version").fetchone()[0]
        assert ver == PLAN_LOG_SCHEMA_VERSION
        cols = {row[1] for row in conn.execute("PRAGMA table_info(plans)").fetchall()}
        for required in (
            "plan_id", "kb_name", "query_hash", "intent",
            "served_by_generation", "served_by_build_id", "cache_status",
            "evidence_ids_json", "warnings_json", "rerank_json",
        ):
            assert required in cols
        step_cols = {row[1] for row in conn.execute("PRAGMA table_info(plan_steps)").fetchall()}
        for required in (
            "plan_id", "step_idx", "tool", "args_json", "observation_json",
            "signal", "decision_source", "tokens", "latency_ms",
        ):
            assert required in step_cols
    finally:
        conn.close()


def test_schema_migration_idempotent(tmp_path, s_settings):
    log = PlanLog("kb-y", s_settings)
    log._get_conn()
    log.close()
    log2 = PlanLog("kb-y", s_settings)
    log2._get_conn()
    db_path = Path(s_settings.storage.data_dir) / "kb-y" / "query_plans.db"
    conn = sqlite3.connect(str(db_path))
    try:
        ver = conn.execute("PRAGMA user_version").fetchone()[0]
        assert ver == PLAN_LOG_SCHEMA_VERSION
    finally:
        conn.close()


def test_schema_unknown_version_raises(tmp_path):
    db = sqlite3.connect(":memory:")
    db.execute(f"PRAGMA user_version = 999")
    with pytest.raises(ServiceError) as exc_info:
        _ensure_schema(db)
    assert exc_info.value.code == ErrorCode.STORAGE_SCHEMA_MISMATCH


# ---------- insert_basic ----------

def test_insert_basic_writes_row(tmp_path, s_settings):
    log = PlanLog("kb-i", s_settings)
    plan = build_plan("hello world", "kb-i", s_settings)
    log.insert_basic(plan)

    db = sqlite3.connect(str(Path(s_settings.storage.data_dir) / "kb-i" / "query_plans.db"))
    try:
        row = db.execute(
            "SELECT plan_id, kb_name, intent, query_hash FROM plans WHERE plan_id = ?",
            (plan.plan_id,),
        ).fetchone()
    finally:
        db.close()
    assert row[0] == plan.plan_id
    assert row[1] == "kb-i"
    assert row[2] == "text_answer"
    assert row[3].startswith("sha256:")


def test_insert_basic_skips_when_persist_false(tmp_path, s_settings):
    s_settings.queryplan.private_kbs = ["kb-priv"]
    log = PlanLog("kb-priv", s_settings)
    plan = build_plan("anything", "kb-priv", s_settings)
    assert plan.persist is False
    log.insert_basic(plan)

    db_path = Path(s_settings.storage.data_dir) / "kb-priv" / "query_plans.db"
    # File should not exist (no connection ever opened)
    assert not db_path.exists()


def test_insert_basic_does_not_raise_on_duplicate(tmp_path, s_settings):
    """Failure-tolerant by contract: never raises."""
    log = PlanLog("kb-d", s_settings)
    plan = build_plan("q", "kb-d", s_settings)
    log.insert_basic(plan)
    # Insert same plan_id again — would normally raise IntegrityError; must be swallowed
    log.insert_basic(plan)


# ---------- update_result_async ----------

def test_update_result_async_writes_basic_then_result(tmp_path, s_settings):
    log = PlanLog("kb-u", s_settings)
    plan = build_plan("q", "kb-u", s_settings)
    log.insert_basic(plan)
    log.update_result_async(
        plan.plan_id,
        {
            "cache_status": "miss",
            "served_by_generation": 1,
            "served_by_build_id": "b-001",
            "evidence_ids": ["e1", "e2"],
            "latency_ms_observed": 123,
            "warnings": ["budget_low"],
        },
    )
    _flush(log)

    db = sqlite3.connect(str(Path(s_settings.storage.data_dir) / "kb-u" / "query_plans.db"))
    try:
        row = db.execute(
            "SELECT cache_status, served_by_generation, served_by_build_id, "
            "evidence_ids_json, latency_ms_observed, warnings_json FROM plans"
        ).fetchone()
    finally:
        db.close()
    assert row[0] == "miss"
    assert row[1] == 1
    assert row[2] == "b-001"
    assert json.loads(row[3]) == ["e1", "e2"]
    assert row[4] == 123
    assert json.loads(row[5]) == ["budget_low"]


def test_update_result_async_partial_does_not_clobber(tmp_path, s_settings):
    log = PlanLog("kb-pp", s_settings)
    plan = build_plan("q", "kb-pp", s_settings)
    log.insert_basic(plan)
    log.update_result_async(plan.plan_id, {"cache_status": "hit"})
    _flush(log)
    log.update_result_async(plan.plan_id, {"latency_ms_observed": 50})
    _flush(log)
    db = sqlite3.connect(str(Path(s_settings.storage.data_dir) / "kb-pp" / "query_plans.db"))
    try:
        row = db.execute("SELECT cache_status, latency_ms_observed FROM plans").fetchone()
    finally:
        db.close()
    assert row[0] == "hit"  # preserved across second update
    assert row[1] == 50


# ---------- plan_steps ----------

def _step(idx: int = 0, *, tool: str = "retrieve") -> StepRecord:
    return StepRecord(
        step_idx=idx,
        tool=tool,
        args={"query": "masked"},
        observation=ToolObservation(
            payload={"result_count": 2},
            tokens_consumed=7,
            latency_ms=12,
            warnings=("stub",),
        ),
        grade=GradeOutcome(top1_score=0.9, margin=0.2, depth=2, signal="no_signal", reason="c1_stub"),
        decision_source="rule",
        rationale="c1_stub",
        ts="2026-05-21T00:00:00Z",
    )


def test_append_and_load_plan_steps(tmp_path, s_settings):
    log = PlanLog("kb-steps", s_settings)
    plan = build_plan("q", "kb-steps", s_settings)
    log.insert_basic(plan)
    log.append_step_async(plan.plan_id, _step(1, tool="retrieve"))
    log.append_step_async(plan.plan_id, _step(2, tool="final"))
    _flush(log)

    rows = log.load_steps(plan.plan_id)
    assert [row.step_idx for row in rows] == [1, 2]
    assert [row.tool for row in rows] == ["retrieve", "final"]
    assert rows[0].args == {"query": "masked"}
    assert rows[0].observation.payload == {"result_count": 2}
    assert rows[0].observation.tokens_consumed == 7
    assert rows[0].grade is not None
    assert rows[0].grade.signal == "no_signal"
    assert log.has_steps(plan.plan_id) is True


def test_has_steps_false_for_classic_plan(tmp_path, s_settings):
    log = PlanLog("kb-no-steps", s_settings)
    plan = build_plan("q", "kb-no-steps", s_settings)
    log.insert_basic(plan)

    assert log.has_steps(plan.plan_id) is False
    assert log.load_steps(plan.plan_id) == []


# ---------- BackgroundWriter overflow ----------

def test_background_writer_overflow_drops_silently():
    """When queue is full, additional enqueues drop without raising."""
    writer = BackgroundWriter(max_queue=2)
    blocker = threading.Event()

    def slow():
        blocker.wait(timeout=2.0)

    # Fill the queue: first item blocks the worker; second waits in queue (capacity=2)
    writer._queue.put_nowait(("x", "", {"__sentinel__": slow}, ""))
    writer._queue.put_nowait(("x", "", {}, ""))
    # Now queue is full; the call below MUST NOT raise
    writer.enqueue("kb-overflow", "/tmp/nope.db", "p", {})
    writer.enqueue("kb-overflow", "/tmp/nope.db", "p", {})
    # Unblock so the test can finish
    blocker.set()
    # No assertion on metric here; metric depends on Metrics implementation. The
    # contract is "doesn't raise" — verified above by reaching this line.


# ---------- prune_expired ----------

def test_prune_expired_deletes_old_rows(tmp_path, s_settings):
    s_settings.queryplan.retention_days = 1
    log = PlanLog("kb-p", s_settings)
    plan = build_plan("q", "kb-p", s_settings)
    log.insert_basic(plan)

    # Backdate the row to 3 days ago
    db_path = Path(s_settings.storage.data_dir) / "kb-p" / "query_plans.db"
    db = sqlite3.connect(str(db_path))
    try:
        db.execute(
            "UPDATE plans SET created_at = ? WHERE plan_id = ?",
            ("2026-05-15T00:00:00Z", plan.plan_id),
        )
        db.commit()
    finally:
        db.close()

    deleted = prune_expired("kb-p", s_settings)
    assert deleted == 1


def test_prune_expired_keeps_fresh_rows(tmp_path, s_settings):
    s_settings.queryplan.retention_days = 30
    log = PlanLog("kb-fresh", s_settings)
    plan = build_plan("q", "kb-fresh", s_settings)
    log.insert_basic(plan)

    deleted = prune_expired("kb-fresh", s_settings)
    assert deleted == 0


def test_prune_expired_handles_missing_db(tmp_path, s_settings):
    deleted = prune_expired("kb-nonexistent", s_settings)
    assert deleted == 0


def test_prune_expired_zero_days_no_op(tmp_path, s_settings):
    """retention_days=0 is treated as "no retention" → don't delete anything."""
    s_settings.queryplan.retention_days = 0
    log = PlanLog("kb-noret", s_settings)
    plan = build_plan("q", "kb-noret", s_settings)
    log.insert_basic(plan)
    deleted = prune_expired("kb-noret", s_settings)
    assert deleted == 0


# ---------- writer thread isolation ----------

def test_writer_survives_update_on_missing_row(tmp_path, s_settings):
    """An UPDATE referencing a non-existent plan_id must not crash worker."""
    log = PlanLog("kb-orphan", s_settings)
    log._get_conn()  # ensure DB exists
    log.update_result_async("nonexistent-plan-id", {"cache_status": "miss"})
    _flush(log)

    # Subsequent inserts still work
    plan = build_plan("q", "kb-orphan", s_settings)
    log.insert_basic(plan)
    db = sqlite3.connect(str(Path(s_settings.storage.data_dir) / "kb-orphan" / "query_plans.db"))
    try:
        count = db.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
    finally:
        db.close()
    assert count == 1
