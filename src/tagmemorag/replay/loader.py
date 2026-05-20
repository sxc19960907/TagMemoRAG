from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..queryplan.plan_log import PLAN_LOG_FILENAME, PLAN_LOG_SCHEMA_VERSION
from .filters import ReplayFilters
from .models import ReplayPlan, SkippedReplayRow

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings


class ReplayLoadError(RuntimeError):
    """Raised when the replay input store itself cannot be read."""


class ReplayPlanLoader:
    """Read replayable QueryPlan rows from per-KB SQLite plan logs."""

    def __init__(self, kb_name: str, settings: "Settings"):
        self.kb_name = kb_name
        self.settings = settings
        self.db_path = Path(settings.storage.data_dir) / kb_name / PLAN_LOG_FILENAME

    def load(
        self,
        *,
        filters: ReplayFilters | None = None,
        limit: int | None = None,
    ) -> tuple[list[ReplayPlan], list[SkippedReplayRow]]:
        filters = filters or ReplayFilters()
        if limit is not None and limit <= 0:
            raise ReplayLoadError("limit must be positive")
        if not self.db_path.exists():
            raise ReplayLoadError(f"query plan log not found: {self.db_path}")

        conn = sqlite3.connect(str(self.db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        try:
            self._check_schema(conn)
            rows = conn.execute(*self._select_sql(filters)).fetchall()
        finally:
            conn.close()

        plans: list[ReplayPlan] = []
        skipped: list[SkippedReplayRow] = []
        for row in rows:
            plan, skip = self._row_to_plan(row)
            if skip is not None:
                skipped.append(skip)
                continue
            if plan is None:
                continue
            if filters.rerank_vendor and _rerank_vendor(plan.rerank) != filters.rerank_vendor:
                continue
            plans.append(plan)
            if limit is not None and len(plans) >= limit:
                break
        return plans, skipped

    def _check_schema(self, conn: sqlite3.Connection) -> None:
        user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if user_version <= 0:
            raise ReplayLoadError(f"invalid query plan log schema version: {user_version}")
        if user_version > PLAN_LOG_SCHEMA_VERSION:
            raise ReplayLoadError(
                f"unsupported query plan log schema version: {user_version} "
                f"(expected <= {PLAN_LOG_SCHEMA_VERSION})"
            )

    def _select_sql(self, filters: ReplayFilters) -> tuple[str, tuple[Any, ...]]:
        where = ["kb_name = ?"]
        params: list[Any] = [self.kb_name]
        if filters.intent:
            where.append("intent = ?")
            params.append(filters.intent)
        if filters.cache_status:
            where.append("cache_status = ?")
            params.append(filters.cache_status)
        if filters.created_after:
            where.append("created_at >= ?")
            params.append(filters.created_after)
        if filters.created_before:
            where.append("created_at <= ?")
            params.append(filters.created_before)
        sql = (
            "SELECT plan_id, kb_name, query_rewrites_masked_json, intent, "
            "filters_json, budget_json, rerank_json, cache_status, "
            "evidence_ids_json, warnings_json, created_at "
            "FROM plans WHERE "
            + " AND ".join(where)
            + " ORDER BY created_at ASC, plan_id ASC"
        )
        return sql, tuple(params)

    def _row_to_plan(self, row: sqlite3.Row) -> tuple[ReplayPlan | None, SkippedReplayRow | None]:
        plan_id = str(row["plan_id"] or "")
        try:
            rewrites = _json_list(row["query_rewrites_masked_json"], "query_rewrites_masked_json")
            query = str(rewrites[0]).strip() if rewrites else ""
            if not query:
                return None, SkippedReplayRow(plan_id, "missing_query")
            filters = _json_dict(row["filters_json"], "filters_json")
            budget = _json_dict(row["budget_json"], "budget_json")
            rerank = _json_optional_dict(row["rerank_json"], "rerank_json")
            evidence_ids = tuple(str(v) for v in _json_optional_list(row["evidence_ids_json"], "evidence_ids_json"))
            warnings = tuple(str(v) for v in _json_optional_list(row["warnings_json"], "warnings_json"))
        except ValueError as exc:
            return None, SkippedReplayRow(plan_id, str(exc))
        return (
            ReplayPlan(
                plan_id=plan_id,
                kb_name=str(row["kb_name"] or self.kb_name),
                query=query,
                created_at=str(row["created_at"] or ""),
                intent=str(row["intent"] or ""),
                filters=filters,
                budget=budget,
                stored_evidence_ids=evidence_ids,
                cache_status=str(row["cache_status"] or ""),
                rerank=rerank,
                warnings=warnings,
            ),
            None,
        )


def _json_list(raw: Any, field: str) -> list[Any]:
    value = _loads_json(raw, field)
    if not isinstance(value, list):
        raise ValueError(f"malformed_{field}")
    return value


def _json_optional_list(raw: Any, field: str) -> list[Any]:
    if raw in (None, ""):
        return []
    return _json_list(raw, field)


def _json_dict(raw: Any, field: str) -> dict[str, Any]:
    value = _loads_json(raw, field)
    if not isinstance(value, dict):
        raise ValueError(f"malformed_{field}")
    return dict(value)


def _json_optional_dict(raw: Any, field: str) -> dict[str, Any] | None:
    if raw in (None, "", "null"):
        return None
    return _json_dict(raw, field)


def _loads_json(raw: Any, field: str) -> Any:
    try:
        return json.loads(str(raw))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed_{field}") from exc


def _rerank_vendor(rerank: dict[str, Any] | None) -> str:
    if not rerank:
        return ""
    return str(rerank.get("vendor_used") or "")


__all__ = ["ReplayLoadError", "ReplayPlanLoader"]
