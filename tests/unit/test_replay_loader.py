from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tagmemorag.config import Settings, StorageConfig
from tagmemorag.queryplan.plan_log import PLAN_LOG_SCHEMA_VERSION, _SCHEMA_V1_SQL
from tagmemorag.replay import ReplayFilters
from tagmemorag.replay.loader import ReplayLoadError, ReplayPlanLoader


@pytest.fixture
def replay_settings(tmp_path: Path) -> Settings:
    return Settings(storage=StorageConfig(data_dir=str(tmp_path / "data")))


def _db_path(cfg: Settings, kb_name: str = "kb-replay") -> Path:
    return Path(cfg.storage.data_dir) / kb_name / "query_plans.db"


def _init_db(cfg: Settings, kb_name: str = "kb-replay") -> Path:
    path = _db_path(cfg, kb_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_SCHEMA_V1_SQL)
        conn.execute(f"PRAGMA user_version = {PLAN_LOG_SCHEMA_VERSION}")
        conn.commit()
    finally:
        conn.close()
    return path


def _insert_plan(
    cfg: Settings,
    *,
    kb_name: str = "kb-replay",
    plan_id: str = "plan-1",
    query_rewrites_masked_json: str | None = None,
    intent: str = "text_answer",
    filters_json: str | None = None,
    budget_json: str | None = None,
    rerank_json: str | None = None,
    cache_status: str | None = "miss",
    evidence_ids_json: str | None = None,
    warnings_json: str | None = None,
    created_at: str = "2026-05-19T10:00:00Z",
) -> None:
    conn = sqlite3.connect(str(_db_path(cfg, kb_name)))
    try:
        conn.execute(
            """
            INSERT INTO plans (
                plan_id, schema_version, kb_name, query_hash,
                query_rewrites_masked_json, intent, filters_json, strategy_json,
                budget_json, rerank_json, cache_status, evidence_ids_json,
                warnings_json, created_at
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                kb_name,
                f"sha256:{plan_id}",
                query_rewrites_masked_json or json.dumps(["蒸汽"], ensure_ascii=False),
                intent,
                filters_json or json.dumps({"brand": "A"}, ensure_ascii=False),
                json.dumps({"indexes": ["vector"]}),
                budget_json or json.dumps({"max_evidence": 5}),
                rerank_json,
                cache_status,
                evidence_ids_json or json.dumps(["ev_001"]),
                warnings_json or json.dumps([]),
                created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_loader_loads_replayable_plan(replay_settings):
    _init_db(replay_settings)
    _insert_plan(
        replay_settings,
        rerank_json=json.dumps({"vendor_used": "noop", "cache_status": "miss"}),
        warnings_json=json.dumps(["reranker_fallback:http_500"]),
    )

    plans, skipped = ReplayPlanLoader("kb-replay", replay_settings).load()

    assert skipped == []
    assert len(plans) == 1
    assert plans[0].plan_id == "plan-1"
    assert plans[0].query == "蒸汽"
    assert plans[0].filters == {"brand": "A"}
    assert plans[0].budget == {"max_evidence": 5}
    assert plans[0].stored_evidence_ids == ("ev_001",)
    assert plans[0].rerank == {"vendor_used": "noop", "cache_status": "miss"}
    assert plans[0].warnings == ("reranker_fallback:http_500",)


def test_loader_missing_db_raises(replay_settings):
    with pytest.raises(ReplayLoadError, match="not found"):
        ReplayPlanLoader("kb-replay", replay_settings).load()


def test_loader_future_schema_raises(replay_settings):
    path = _init_db(replay_settings)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA user_version = 999")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ReplayLoadError, match="unsupported"):
        ReplayPlanLoader("kb-replay", replay_settings).load()


def test_loader_skips_malformed_json_rows(replay_settings):
    _init_db(replay_settings)
    _insert_plan(replay_settings, plan_id="bad-rewrite", query_rewrites_masked_json="{")
    _insert_plan(replay_settings, plan_id="bad-budget", budget_json="{")
    _insert_plan(replay_settings, plan_id="good", created_at="2026-05-19T10:01:00Z")

    plans, skipped = ReplayPlanLoader("kb-replay", replay_settings).load()

    assert [p.plan_id for p in plans] == ["good"]
    assert {s.plan_id: s.reason for s in skipped} == {
        "bad-rewrite": "malformed_query_rewrites_masked_json",
        "bad-budget": "malformed_budget_json",
    }


def test_loader_skips_blank_query(replay_settings):
    _init_db(replay_settings)
    _insert_plan(replay_settings, query_rewrites_masked_json=json.dumps(["  "]))

    plans, skipped = ReplayPlanLoader("kb-replay", replay_settings).load()

    assert plans == []
    assert skipped[0].reason == "missing_query"


def test_loader_applies_sql_filters(replay_settings):
    _init_db(replay_settings)
    _insert_plan(replay_settings, plan_id="old", intent="text_answer", cache_status="hit", created_at="2026-05-01T00:00:00Z")
    _insert_plan(replay_settings, plan_id="keep", intent="troubleshooting", cache_status="miss", created_at="2026-05-10T00:00:00Z")
    _insert_plan(replay_settings, plan_id="new", intent="troubleshooting", cache_status="miss", created_at="2026-05-20T00:00:00Z")

    plans, skipped = ReplayPlanLoader("kb-replay", replay_settings).load(
        filters=ReplayFilters(
            intent="troubleshooting",
            cache_status="miss",
            created_after="2026-05-02T00:00:00Z",
            created_before="2026-05-19T23:59:59Z",
        )
    )

    assert skipped == []
    assert [p.plan_id for p in plans] == ["keep"]


def test_loader_applies_rerank_vendor_filter(replay_settings):
    _init_db(replay_settings)
    _insert_plan(replay_settings, plan_id="noop", rerank_json=json.dumps({"vendor_used": "noop"}))
    _insert_plan(replay_settings, plan_id="sf", rerank_json=json.dumps({"vendor_used": "siliconflow"}))
    _insert_plan(replay_settings, plan_id="none", rerank_json=None)

    plans, _ = ReplayPlanLoader("kb-replay", replay_settings).load(
        filters=ReplayFilters(rerank_vendor="siliconflow")
    )

    assert [p.plan_id for p in plans] == ["sf"]


def test_loader_applies_limit_after_filters(replay_settings):
    _init_db(replay_settings)
    for i in range(5):
        _insert_plan(
            replay_settings,
            plan_id=f"p{i}",
            rerank_json=json.dumps({"vendor_used": "noop" if i % 2 else "sf"}),
            created_at=f"2026-05-19T10:0{i}:00Z",
        )

    plans, _ = ReplayPlanLoader("kb-replay", replay_settings).load(
        filters=ReplayFilters(rerank_vendor="noop"),
        limit=2,
    )

    assert [p.plan_id for p in plans] == ["p1", "p3"]


def test_loader_rejects_non_positive_limit(replay_settings):
    _init_db(replay_settings)
    with pytest.raises(ReplayLoadError, match="limit"):
        ReplayPlanLoader("kb-replay", replay_settings).load(limit=0)
