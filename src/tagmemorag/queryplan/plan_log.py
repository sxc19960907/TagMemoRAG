"""Per-KB SQLite plan log (Architecture v2 § A2 / Decisions D1 + D5 + D7).

Two-phase write model:
- insert_basic(plan): synchronous; called BEFORE response returns; failures
  swallowed + metric. Writes basic columns (plan_id, kb_name, query_hash,
  intent, filters_json, strategy_json, budget_json, query_rewrites_masked_json,
  created_at, schema_version).
- update_result_async(plan_id, result_dict): non-blocking; queued on a
  shared BackgroundWriter thread that flushes UPDATEs serially. Writes
  served_by_*, cache_status, evidence_ids_json, latency_ms_observed,
  warnings_json, rerank_json.

Schema is versioned via PRAGMA user_version. Schema migration runs on first
connect; unknown future versions raise STORAGE_SCHEMA_MISMATCH.
"""

from __future__ import annotations

import json
import queue
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from ..errors import ErrorCode, ServiceError
from ..observability.metrics import get_metrics
from .plan import QueryPlan

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings
    from ..agentic.state import StepRecord


PLAN_LOG_FILENAME = "query_plans.db"
PLAN_LOG_SCHEMA_VERSION = 1
_LOGGER = structlog.get_logger()


_SCHEMA_V1_SQL = """
CREATE TABLE plans (
    plan_id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL DEFAULT 1,
    kb_name TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    query_rewrites_masked_json TEXT NOT NULL,
    intent TEXT NOT NULL,
    filters_json TEXT NOT NULL,
    strategy_json TEXT NOT NULL,
    budget_json TEXT NOT NULL,
    rerank_json TEXT,
    served_by_generation INTEGER,
    served_by_build_id TEXT,
    cache_status TEXT,
    evidence_ids_json TEXT,
    latency_ms_observed INTEGER,
    warnings_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_plans_kb_created ON plans(kb_name, created_at);
CREATE INDEX idx_plans_kb_generation ON plans(kb_name, served_by_generation);
CREATE INDEX idx_plans_kb_intent ON plans(kb_name, intent);
"""

_CREATE_STEPS_SQL = """
CREATE TABLE IF NOT EXISTS plan_steps (
    plan_id TEXT NOT NULL,
    step_idx INTEGER NOT NULL,
    tool TEXT NOT NULL,
    args_json TEXT NOT NULL,
    observation_json TEXT NOT NULL,
    signal TEXT NOT NULL,
    decision_source TEXT NOT NULL,
    top1_score REAL,
    margin REAL,
    depth INTEGER,
    rationale TEXT,
    tokens INTEGER,
    latency_ms INTEGER,
    ts TEXT NOT NULL,
    PRIMARY KEY (plan_id, step_idx)
)
"""

_INSERT_BASIC_SQL = """
INSERT INTO plans (
    plan_id, schema_version, kb_name, query_hash,
    query_rewrites_masked_json, intent, filters_json, strategy_json,
    budget_json, created_at
) VALUES (
    :plan_id, :schema_version, :kb_name, :query_hash,
    :query_rewrites_masked_json, :intent, :filters_json, :strategy_json,
    :budget_json, :created_at
)
"""

_UPDATE_RESULT_SQL = """
UPDATE plans SET
    rerank_json = COALESCE(:rerank_json, rerank_json),
    served_by_generation = COALESCE(:served_by_generation, served_by_generation),
    served_by_build_id = COALESCE(:served_by_build_id, served_by_build_id),
    cache_status = COALESCE(:cache_status, cache_status),
    evidence_ids_json = COALESCE(:evidence_ids_json, evidence_ids_json),
    latency_ms_observed = COALESCE(:latency_ms_observed, latency_ms_observed),
    warnings_json = COALESCE(:warnings_json, warnings_json)
WHERE plan_id = :plan_id
"""

_INSERT_STEP_SQL = """
INSERT OR REPLACE INTO plan_steps (
    plan_id, step_idx, tool, args_json, observation_json,
    signal, decision_source, top1_score, margin, depth,
    rationale, tokens, latency_ms, ts
) VALUES (
    :plan_id, :step_idx, :tool, :args_json, :observation_json,
    :signal, :decision_source, :top1_score, :margin, :depth,
    :rationale, :tokens, :latency_ms, :ts
)
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Run migration on first connect.

    Schema version map:
      0 → fresh DB, install v1.
      1 → already current, no-op.
      else → raise STORAGE_SCHEMA_MISMATCH.
    """
    user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if user_version == 0:
        conn.executescript(_SCHEMA_V1_SQL)
        conn.execute(_CREATE_STEPS_SQL)
        conn.execute(f"PRAGMA user_version = {PLAN_LOG_SCHEMA_VERSION}")
        conn.commit()
        return
    if user_version == PLAN_LOG_SCHEMA_VERSION:
        conn.execute(_CREATE_STEPS_SQL)
        conn.commit()
        return
    raise ServiceError(
        ErrorCode.STORAGE_SCHEMA_MISMATCH,
        f"Unknown plan log schema version: {user_version}",
        {"actual": user_version, "expected": PLAN_LOG_SCHEMA_VERSION},
    )


# ---------- BackgroundWriter ----------

class BackgroundWriter:
    """Single-thread queue-flushing worker shared across KBs.

    Bounded queue; on overflow, NEW items are DROPPED with metrics increment
    (drop preferred over blocking the API thread).
    """

    def __init__(self, max_queue: int = 1024):
        self._queue: queue.Queue[tuple[str, str, dict, str, str]] = queue.Queue(maxsize=max_queue)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="queryplan-writer")
        self._thread.start()

    def enqueue(self, kb_name: str, db_path: str, plan_id: str, result: dict) -> None:
        self.enqueue_update(kb_name, db_path, plan_id, result)

    def enqueue_update(self, kb_name: str, db_path: str, plan_id: str, result: dict) -> None:
        try:
            self._queue.put_nowait(("update", kb_name, db_path, result, plan_id))
        except queue.Full:
            get_metrics().record_plan_log_event(kb_name=kb_name, event="queue_overflow")

    def enqueue_step(self, kb_name: str, db_path: str, plan_id: str, row: dict) -> None:
        try:
            self._queue.put_nowait(("step", kb_name, db_path, row, plan_id))
        except queue.Full:
            get_metrics().record_plan_log_event(kb_name=kb_name, event="queue_overflow")

    def flush(self, timeout: float = 2.0) -> None:
        """Test-helper: block until queue empty (or timeout)."""
        end = threading.Event()

        def _sentinel():
            end.set()

        # Push a sentinel; when worker processes it, end is set.
        try:
            self._queue.put_nowait(("sentinel", "__sentinel__", "", {"__sentinel__": _sentinel}, ""))
        except queue.Full:
            return
        end.wait(timeout=timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if len(item) == 4:
                kb_name, db_path, result, plan_id = item
                kind = "update"
            else:
                kind, kb_name, db_path, result, plan_id = item
            # Sentinel handling for tests
            if kind == "sentinel" or kb_name == "__sentinel__":
                fn = result.get("__sentinel__")
                if callable(fn):
                    try:
                        fn()
                    except Exception:  # noqa: BLE001
                        pass
                continue
            try:
                if kind == "step":
                    _do_insert_step(db_path, result)
                else:
                    _do_update(db_path, plan_id, result)
            except Exception as exc:  # noqa: BLE001
                event = "step_insert_failed" if kind == "step" else "update_failed"
                get_metrics().record_plan_log_event(kb_name=kb_name, event=event)
                _LOGGER.warning(
                    "plan_log_write_failed",
                    write_kind=kind,
                    kb_name=kb_name,
                    plan_id=plan_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )


_shared_writer_lock = threading.Lock()
_shared_writer_instance: BackgroundWriter | None = None


def _shared_writer(max_queue: int = 1024) -> BackgroundWriter:
    global _shared_writer_instance
    with _shared_writer_lock:
        if _shared_writer_instance is None:
            _shared_writer_instance = BackgroundWriter(max_queue=max_queue)
    return _shared_writer_instance


def _reset_shared_writer_for_tests() -> None:
    """Test-helper: drop the shared writer so each test sees a fresh one."""
    global _shared_writer_instance
    with _shared_writer_lock:
        if _shared_writer_instance is not None:
            _shared_writer_instance._stop.set()
        _shared_writer_instance = None


def _do_update(db_path: str, plan_id: str, result: dict) -> None:
    """Run a single UPDATE in a fresh connection (one-shot).

    Reasoning: per-update connection avoids holding cross-thread state and
    lets sqlite handle WAL serialization. Cost: extra open/close, but UPDATE
    is rare relative to reads.
    """
    if not db_path:
        return
    conn = sqlite3.connect(db_path, timeout=2.0)
    try:
        params = {
            "plan_id": plan_id,
            "rerank_json": result.get("rerank_json"),
            "served_by_generation": result.get("served_by_generation"),
            "served_by_build_id": result.get("served_by_build_id"),
            "cache_status": result.get("cache_status"),
            "evidence_ids_json": result.get("evidence_ids_json"),
            "latency_ms_observed": result.get("latency_ms_observed"),
            "warnings_json": result.get("warnings_json"),
        }
        conn.execute(_UPDATE_RESULT_SQL, params)
        conn.commit()
    finally:
        conn.close()


def _do_insert_step(db_path: str, row: dict) -> None:
    if not db_path:
        return
    conn = sqlite3.connect(db_path, timeout=2.0)
    try:
        _ensure_schema(conn)
        conn.execute(_INSERT_STEP_SQL, row)
        conn.commit()
    finally:
        conn.close()


# ---------- PlanLog ----------

class PlanLog:
    """Per-KB SQLite plan log adapter.

    Single connection per instance, lazy init, WAL mode, check_same_thread=False
    so the BackgroundWriter (separate thread) can issue UPDATEs through fresh
    connections to the same file.
    """

    def __init__(self, kb_name: str, settings: "Settings"):
        self.kb_name = kb_name
        self.settings = settings
        self._conn: sqlite3.Connection | None = None
        self._db_path = self._compute_db_path()
        self._writer = _shared_writer(
            max_queue=int(settings.queryplan.background_writer_max_queue)
        )

    def _compute_db_path(self) -> str:
        path = Path(self.settings.storage.data_dir) / self.kb_name / PLAN_LOG_FILENAME
        return str(path)

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                self._db_path, check_same_thread=False, timeout=2.0
            )
            self._conn.execute("PRAGMA journal_mode = WAL")
            _ensure_schema(self._conn)
        return self._conn

    def insert_basic(self, plan: QueryPlan) -> None:
        """Sync write of basic columns. Failures swallowed + metric; never raised."""
        if not plan.persist:
            return
        try:
            conn = self._get_conn()
            conn.execute(_INSERT_BASIC_SQL, plan.to_basic_dict())
            conn.commit()
            get_metrics().record_plan_log_event(kb_name=self.kb_name, event="insert_ok")
        except Exception as exc:  # noqa: BLE001
            get_metrics().record_plan_log_event(kb_name=self.kb_name, event="insert_failed")
            _LOGGER.warning(
                "plan_log_insert_failed",
                kb_name=self.kb_name,
                plan_id=plan.plan_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

    def update_result_async(self, plan_id: str, result: dict[str, Any]) -> None:
        """Queue a result UPDATE. Non-blocking. Drops on overflow."""
        # Normalize JSON-bearing fields if caller passed lists/dicts.
        normalized: dict[str, Any] = {}
        for k, v in result.items():
            if k in ("evidence_ids", "warnings"):
                normalized[f"{k}_json"] = json.dumps(v, ensure_ascii=False) if v is not None else None
            elif k == "rerank":
                normalized["rerank_json"] = json.dumps(v, ensure_ascii=False) if v is not None else None
            else:
                normalized[k] = v
        self._writer.enqueue(self.kb_name, self._db_path, plan_id, normalized)

    def append_step_async(self, plan_id: str, record: "StepRecord") -> None:
        """Queue a plan_steps insert. Non-blocking. Drops on overflow."""
        row = _step_record_row(plan_id, record)
        self._writer.enqueue_step(self.kb_name, self._db_path, plan_id, row)

    def load_steps(self, plan_id: str) -> list["StepRecord"]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT step_idx, tool, args_json, observation_json, signal, "
            "decision_source, top1_score, margin, depth, rationale, tokens, "
            "latency_ms, ts FROM plan_steps WHERE plan_id = ? ORDER BY step_idx ASC",
            (plan_id,),
        ).fetchall()
        return [_row_to_step_record(row) for row in rows]

    def has_steps(self, plan_id: str) -> bool:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM plan_steps WHERE plan_id = ? LIMIT 1",
            (plan_id,),
        ).fetchone()
        return row is not None

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None


def prune_expired(kb_name: str, settings: "Settings") -> int:
    """Delete plans older than retention_days. Admin-callable; T2 does NOT auto-trigger.

    Returns the number of rows deleted.
    """
    days = int(settings.queryplan.retention_days)
    if days <= 0:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db_path = str(Path(settings.storage.data_dir) / kb_name / PLAN_LOG_FILENAME)
    if not Path(db_path).exists():
        return 0
    conn = sqlite3.connect(db_path, timeout=2.0)
    try:
        _ensure_schema(conn)
        cur = conn.execute(
            "DELETE FROM plans WHERE kb_name = ? AND created_at < ?",
            (kb_name, cutoff),
        )
        conn.commit()
        deleted = cur.rowcount or 0
        if deleted > 0:
            get_metrics().record_plan_log_event(
                kb_name=kb_name, event="pruned", count=deleted
            )
        return deleted
    finally:
        conn.close()


def _step_record_row(plan_id: str, record: "StepRecord") -> dict[str, Any]:
    grade = record.grade
    return {
        "plan_id": plan_id,
        "step_idx": int(record.step_idx),
        "tool": record.tool,
        "args_json": json.dumps(record.args, ensure_ascii=False, sort_keys=True),
        "observation_json": json.dumps(record.observation.to_dict(), ensure_ascii=False, sort_keys=True),
        "signal": grade.signal if grade is not None else "no_signal",
        "decision_source": record.decision_source,
        "top1_score": grade.top1_score if grade is not None else None,
        "margin": grade.margin if grade is not None else None,
        "depth": grade.depth if grade is not None else None,
        "rationale": record.rationale,
        "tokens": int(record.observation.tokens_consumed),
        "latency_ms": int(record.observation.latency_ms),
        "ts": record.ts,
    }


def _row_to_step_record(row: sqlite3.Row | tuple[Any, ...]) -> "StepRecord":
    from ..agentic.state import GradeOutcome, StepRecord, ToolObservation

    (
        step_idx,
        tool,
        args_json,
        observation_json,
        signal,
        decision_source,
        top1_score,
        margin,
        depth,
        rationale,
        _tokens,
        _latency_ms,
        ts,
    ) = row
    grade = GradeOutcome(
        top1_score=float(top1_score or 0.0),
        margin=float(margin or 0.0),
        depth=int(depth or 0),
        signal=str(signal or "no_signal"),  # type: ignore[arg-type]
        reason=str(rationale or ""),
    )
    return StepRecord(
        step_idx=int(step_idx),
        tool=str(tool),
        args=json.loads(str(args_json or "{}")),
        observation=ToolObservation.from_dict(json.loads(str(observation_json or "{}"))),
        grade=grade,
        decision_source=str(decision_source or "rule"),  # type: ignore[arg-type]
        rationale=str(rationale or ""),
        ts=str(ts or ""),
    )


__all__ = [
    "BackgroundWriter",
    "PLAN_LOG_FILENAME",
    "PLAN_LOG_SCHEMA_VERSION",
    "PlanLog",
    "prune_expired",
]
