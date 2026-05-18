# T2 — QueryPlan + Budget contract + SQLite plan log — Implementation Checklist

8 slices. Each independently reviewable; commits roll up at slice boundaries. Pattern follows T1.

## Pre-flight

- [ ] Confirm git tree clean.
- [ ] Confirm active task: `python3 ./.trellis/scripts/task.py current --source` returns this task.
- [ ] Re-read `prd.md` D1–D8 and `design.md` § 1–12.
- [ ] Eval slice: existing fixtures + `test_m2_api.py` + new unit tests; nothing requires shadow-build flow but the new private-KB path must be exercised.

## Slice 0 — Settings: add `QueryPlanConfig`

- [ ] Add `QueryPlanConfig` to `src/tagmemorag/config.py`: `persist_enabled`, `retention_days`, `private_kbs`, `default_*` fields, `out_of_scope_keywords`, `pii_mask_rules`, `background_writer_max_queue`.
- [ ] Add `Settings.queryplan: QueryPlanConfig`.
- [ ] Tests: round-trip defaults; explicit override; env var override.
- [ ] Commit: `feat(queryplan): T2 Slice 0 — add QueryPlanConfig settings block`.

## Slice 1 — `Budget` and `QueryPlan` dataclasses

- [ ] New module `src/tagmemorag/queryplan/__init__.py` exporting public API.
- [ ] `src/tagmemorag/queryplan/plan.py` with `Intent` enum, `Budget`, `QueryPlan` (frozen, eq=False due to Settings/dict fields).
- [ ] JSON serialization helpers: `to_basic_dict`, `to_result_dict`, `from_dict`. `deadline_at` excluded from serialization.
- [ ] Tests: round-trip (basic + result); deadline_at not serialized; Intent enum stringification.
- [ ] Commit: `feat(queryplan): T2 Slice 1 — Budget + QueryPlan dataclasses`.

## Slice 2 — Rule-based planner + intent + privacy mask

- [ ] `src/tagmemorag/queryplan/intent.py:classify_intent` with `DEFAULT_OUT_OF_SCOPE_KEYWORDS`.
- [ ] `src/tagmemorag/queryplan/privacy.py:mask_rewrites` (passthrough when rules=None).
- [ ] `src/tagmemorag/queryplan/planner.py:build_plan(request, kb_name, settings)` per design § 3.2.
- [ ] BudgetGuard at `src/tagmemorag/queryplan/budget.py`.
- [ ] Tests: build_plan completeness; private-KB short-circuit (`persist=False`, `allow_external_reranker=False`); intent classification; mask passthrough + rule-applied; BudgetGuard exhaustion math.
- [ ] Commit: `feat(queryplan): T2 Slice 2 — rule-based planner + intent + privacy + guard`.

## Slice 3 — SQLite plan log + BackgroundWriter

- [ ] `src/tagmemorag/queryplan/plan_log.py:PlanLog` per design § 4.
- [ ] Schema migration via `PRAGMA user_version`; v1 schema embedded as constant.
- [ ] `BackgroundWriter` singleton with bounded queue; overflow drops + metric.
- [ ] `prune_expired(kb, settings)` retention helper.
- [ ] Metrics: register `plan_log_event` counter (insert_failed / update_failed / queue_overflow / pruned).
- [ ] Tests: schema migration; insert_basic; update_result_async with synchronous flush in test; retention pruning; queue overflow drops + counter; corrupted PRAGMA error.
- [ ] Commit: `feat(queryplan): T2 Slice 3 — SQLite plan log with two-phase write`.

## Slice 4 — SearchRequest / RetrieveRequest accept BudgetSpec

- [ ] Add `BudgetSpec` pydantic model in `api.py`.
- [ ] `SearchRequest.budget: BudgetSpec | None = None`.
- [ ] Resolution helper `_resolve_budget(spec, settings) -> Budget` (defaults from Settings.queryplan).
- [ ] Tests: request with no budget uses settings defaults; request with partial budget fills missing fields; request with all-None budget treated as None.
- [ ] Commit: `feat(queryplan): T2 Slice 4 — SearchRequest budget field`.

## Slice 5 — Wire `/search` + `/retrieve` to plan log

- [ ] In `_search_impl`: build_plan → insert_basic → guard checks at each stage → update_result_async.
- [ ] Same in `_retrieve_impl`.
- [ ] Out-of-scope short-circuit: skip retrieval, write plan log with `cache_status="disabled"`, return empty results + warning.
- [ ] Cache hit path: write plan with `cache_status="hit"`; cache miss: `"miss"`.
- [ ] Response models add `plan_id: str` and `warnings: list[str] | None`.
- [ ] Tests: `/search` returns plan_id; `/retrieve` returns plan_id; cache hit produces fresh plan_id; private KB does not persist; forced low budget returns warnings.
- [ ] Commit: `feat(queryplan): T2 Slice 5 — wire /search and /retrieve to plan log`.

## Slice 6 — `SearchFeedback` adds plan_id

- [ ] `SearchFeedback` dataclass: `plan_id: str = ""`.
- [ ] `feedback_from_payload`: parse optional `plan_id` (default "").
- [ ] `SearchFeedback.to_dict`: include `plan_id`.
- [ ] `FeedbackSubmitRequest.plan_id: str | None = None`.
- [ ] Tests: jsonl row without plan_id parses with empty string; jsonl row with plan_id round-trips; admin feedback list includes plan_id.
- [ ] Commit: `feat(queryplan): T2 Slice 6 — feedback dataclass adds plan_id`.

## Slice 7 — architecture.md + memory updates

- [ ] architecture.md A2 status: 🚧 → ✅; add storage paragraph linking to `query_plans.db`.
- [ ] If T2 implementation surfaced design gaps (per T1 pattern), append D-records to PRD.
- [ ] New memory `t2-queryplan-mechanism-key-points.md` (reference type) describing the API contract.
- [ ] If new lessons learned, append to `t1-implementation-lessons.md` or create `t2-implementation-lessons.md`.
- [ ] Commit: `docs(spec): T2 Slice 7 — architecture.md + memory updates`.

## Final Validation

```bash
uv run pytest tests/unit -x --no-header -q --ignore=tests/unit/test_diag_realmanuals_eval.py
git diff --check
```

All must pass. Eval slice deltas reported in commit message.

## Review Gates

- [ ] After Slice 3: smoke test `PlanLog` against a tmp_path KB.
- [ ] After Slice 5: full unit + integration suite green.
- [ ] After Slice 7: user review before declaring task complete.

## Rollback

Each slice's commit is independently revertable. Slice 5 is the only one that touches request paths; reverting Slices 5+6 leaves the new modules dormant (no API consumers) — safe partial rollback.

## Out-of-Band Notes

- T3 will reuse `RerankSpec` slot in QueryPlan; do not lock the schema beyond what design § 2.3 calls.
- T5 (replay tool) will implement `prune_expired` scheduling and read SQL queries; T2 only ships the substrate.
- If T2 surfaces a fundamental performance issue with SQLite contention at burst (unlikely at current QPS), surface via [[trellis-update-spec]] rather than silently moving to PG.
